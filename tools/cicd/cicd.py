import datetime
import logging
import shutil
from importlib import import_module
from io import StringIO
from os import chdir, getcwd
from pathlib import Path
from subprocess import check_output
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import click
import jsonpatchplus
import yaml


DirPath = click.Path(exists=False, file_okay=False, path_type=Path)
ExistingDirPath = click.Path(exists=True, file_okay=False, path_type=Path)

header = """# Copyright (c) {} AccelByte Inc. All Rights Reserved.
# This is licensed software from AccelByte Inc, for limitations
# and restrictions contact your company contract manager.
""".format(
    datetime.date.today().year
)

modes = {
    "default": {
        "proto": "templates/proto.j2",
        "m2mc": "templates/message-message_class-map-properties.j2",
        "t2sc": "templates/topic-service_class-map-properties.j2",
        "mcf": "topicMessageToMessageClassMapping.properties",
        "scf": "topicMessageToServiceClassMapping.properties",
    },
    "1rpc1s": {
        "proto": "templates/proto-1rpc1s.j2",
        "m2mc": "templates/message-message_class-map-properties-1rpc1s.j2",
        "t2sc": "templates/topic-service_class-map-properties-1rpc1s.j2",
        "mcf": "topicMessageToMessageClassMapping.properties",
        "scf": "topicMessageToServiceClassMapping.properties",
    }
}
fopen_kwargs = {"encoding": "utf-8", "errors": "ignore"}
mkdir_kwargs = {"parents": True, "exist_ok": True}
render_kwargs = {
    "input_processor": "raw",
    "template_processor": "textf",
    "renderer": "default",
    "extension": [
        "*default",
        "*jinja",
        "accelbyte_codegen.ext.asyncapi.protobuf.extension.AsyncAPI2ProtobufExtension",
    ],
    "loader": "templates",
}
safe_dump_kwargs = {"sort_keys": False}


def import_module_attr(module_name: str, attr_name: str) -> Optional[Any]:
    try:
        module = import_module(module_name)
    except ModuleNotFoundError:
        return None
    try:
        attr = getattr(module, attr_name)
    except AttributeError:
        return None
    return attr


logger = logging.getLogger()
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)

imports = SimpleNamespace(
    render=import_module_attr("accelbyte_codegen.cli.render", "render"),
    to_camel_case=import_module_attr(
        "accelbyte_codegen.utils.casestyle", "to_camel_case"
    ),
    to_pascal_case=import_module_attr(
        "accelbyte_codegen.utils.casestyle", "to_pascal_case"
    ),
    to_snake_case=import_module_attr(
        "accelbyte_codegen.utils.casestyle", "to_snake_case"
    ),
    processor_class=import_module_attr(
        "accelbyte_codegen.ext.asyncapi.processor.v2", "AsyncAPIInputProcessor"
    ),
)


@click.command()
@click.argument("template_dir", type=ExistingDirPath)
@click.argument("source_dir", type=ExistingDirPath)
@click.argument("destination_dir", type=DirPath)
@click.option("--mode")
def run(
    template_dir: Path,
    source_dir: Path,
    destination_dir: Path,
    mode: Optional[str] = None,
) -> None:
    template_dir_copy = destination_dir / template_dir.name
    if template_dir_copy.exists():
        shutil.rmtree(template_dir_copy, ignore_errors=True)
    shutil.copytree(template_dir, template_dir_copy)
    logging.info("copied from '%s' to '%s'", template_dir, template_dir_copy)

    git_hash = try_get_git_hash(path=source_dir)

    for template in sorted(template_dir_copy.glob("**/config.yaml")):
        obj = yaml.safe_load(template.read_text(**fopen_kwargs))

        src_orig = source_dir / obj["source"]

        if not src_orig.exists():
            logging.warning("'%s' does not exist!", src_orig.relative_to(source_dir))
            continue

        if not src_orig.is_file():
            logging.warning("'%s' is not a file!", src_orig.relative_to(source_dir))
            continue

        vendor_properties = {"x-source": obj["source"]}
        if git_hash:
            vendor_properties["x-git-hash"] = git_hash

        # 1. Copy
        src_copy = destination_dir / "original" / obj["source"]
        copy(
            source_file=src_orig,
            destination_file=src_copy,
            source_dir=source_dir,
            destination_dir=destination_dir,
        )

        # 2. Patch
        src_patch = destination_dir / "patched" / obj["source"]
        patch(
            source_file=src_copy,
            destination_file=src_patch,
            patch_files=list(template.parent.glob("*.patch.yaml")),
            destination_dir=destination_dir,
            vendor_properties=vendor_properties,
        )

        dst = destination_dir / obj["destination"]

        # 3.a. Convert to .proto
        dst_proto = dst.with_suffix(".proto")
        success_proto = convert_to_proto(
            source_file=src_patch,
            destination_file=dst_proto,
            source_dir=destination_dir,
            destination_dir=destination_dir,
            mode=mode,
        )

        # 3.b. Convert to .mc.properties
        if success_proto:
            dst_proto = dst.parent / f"{dst.stem}.mc.properties"
            convert_to_message_class_map_properties(
                source_file=src_patch,
                destination_file=dst_proto,
                source_dir=destination_dir,
                destination_dir=destination_dir,
                mode=mode,
            )

        # 3.c. Convert to .sc.properties
        if success_proto:
            dst_proto = dst.parent / f"{dst.stem}.sc.properties"
            convert_to_service_class_map_properties(
                source_file=src_patch,
                destination_file=dst_proto,
                source_dir=destination_dir,
                destination_dir=destination_dir,
                mode=mode,
            )

        if success_proto:
            logging.info("---- '%s' done\n", template.relative_to(template_dir_copy))
        else:
            logging.warning("---- '%s' error\n", template.relative_to(template_dir_copy))

    # 4.a Merge .mc.properties files
    dst_mc_properties = destination_dir / modes.get(mode, modes["default"]).get("mcf")
    merge_files(
        source_dir=destination_dir,
        destination_file=dst_mc_properties,
        file_extension=".mc.properties",
        prefix=header,
        destination_dir=destination_dir,
    )

    logging.info("---- merging .mc.properties done\n")

    # 4.b Merge .sc.properties files
    dst_mc_properties = destination_dir / modes.get(mode, modes["default"]).get("scf")
    merge_files(
        source_dir=destination_dir,
        destination_file=dst_mc_properties,
        file_extension=".sc.properties",
        prefix=header,
        destination_dir=destination_dir,
    )

    logging.info("---- merging .sc.properties done\n")

    # 5. Add TIMESTAMP
    timestamp_file = destination_dir / "TIMESTAMP"
    timestamp(destination_file=timestamp_file, destination_dir=destination_dir)


# noinspection PyBroadException, PyShadowingBuiltins
def convert_to_message_class_map_properties(
    source_file: Path,
    destination_file: Path,
    source_dir: Optional[Path] = None,
    destination_dir: Optional[Path] = None,
    mode: Optional[str] = None,
) -> bool:
    if not all(imports.__dict__.values()):
        logging.warning(
            "[er] conversion dependencies missing, skipping '%s'!",
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
        return False

    try:
        input = imports.processor_class()(str(source_file))
        imports.render(
            input=input,
            template=modes.get(mode, modes["default"]).get("m2mc"),
            output=destination_file,
            **render_kwargs,
        )
        logging.info(
            "[ok] converted from '%s' to '%s' (%s)",
            source_file.name
            if source_dir is None
            else source_file.relative_to(source_dir),
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
            mode,
        )
    except Exception as error:
        logging.warning(
            "[er] conversion failed due to [%s]: %s, skipping '%s'!",
            error.__class__.__name__,
            error,
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
        return False
    return True


# noinspection PyBroadException, PyShadowingBuiltins
def convert_to_service_class_map_properties(
    source_file: Path,
    destination_file: Path,
    source_dir: Optional[Path] = None,
    destination_dir: Optional[Path] = None,
    mode: Optional[str] = None,
) -> bool:
    if not all(imports.__dict__.values()):
        logging.warning(
            "[er] conversion dependencies missing, skipping '%s'!",
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
        return False

    try:
        input = imports.processor_class()(str(source_file))
        imports.render(
            input=input,
            template=modes.get(mode, modes["default"]).get("t2sc"),
            output=destination_file,
            **render_kwargs,
        )
        logging.info(
            "[ok] converted from '%s' to '%s' (%s)",
            source_file.name
            if source_dir is None
            else source_file.relative_to(source_dir),
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
            mode,
        )
    except Exception as error:
        logging.warning(
            "[er] conversion failed due to [%s]: %s, skipping '%s'!",
            error.__class__.__name__,
            error,
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
        return False
    return True


# noinspection PyBroadException, PyShadowingBuiltins
def convert_to_proto(
    source_file: Path,
    destination_file: Path,
    source_dir: Optional[Path] = None,
    destination_dir: Optional[Path] = None,
    mode: Optional[str] = None,
) -> bool:
    if not all(imports.__dict__.values()):
        logging.warning(
            "[er] conversion dependencies missing, skipping '%s'!",
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
        return False

    try:
        input = imports.processor_class()(str(source_file))
        imports.render(
            input=input,
            template=modes.get(mode, modes["default"]).get("proto"),
            output=destination_file,
            **render_kwargs,
        )
        logging.info(
            "[ok] converted from '%s' to '%s' (%s)",
            source_file.name
            if source_dir is None
            else source_file.relative_to(source_dir),
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
            mode,
        )
    except Exception as error:
        logging.warning(
            "[er] conversion failed due to [%s]: %s, skipping '%s'!",
            error.__class__.__name__,
            error,
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
        return False
    return True


def copy(
    source_file: Path,
    destination_file: Path,
    source_dir: Optional[Path] = None,
    destination_dir: Optional[Path] = None,
) -> None:
    destination_file.parent.mkdir(**mkdir_kwargs)
    shutil.copyfile(source_file, destination_file)
    logging.info(
        "[ok] copied from '%s' to '%s'",
        source_file.name if source_dir is None else source_file.relative_to(source_dir),
        destination_file.name
        if destination_dir is None
        else destination_file.relative_to(destination_dir),
    )


def merge_files(
    source_dir: Path,
    destination_file: Path,
    file_extension: str,
    prefix: str = "",
    suffix: str = "",
    destination_dir: Optional[Path] = None,
) -> None:
    sio = StringIO()

    sio.write(prefix)

    for file in sorted(source_dir.glob(f"**/*{file_extension}")):
        sio.write("\n{}".format(file.read_text(**fopen_kwargs)))
        logging.debug(
            "[ok] appended contents of '%s' to '%s'",
            file.name,
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )

    sio.write(suffix)

    destination_file.parent.mkdir(**mkdir_kwargs)
    destination_file.write_text(sio.getvalue())


def patch(
    source_file: Path,
    destination_file: Path,
    patch_files: List[Path],
    destination_dir: Optional[Path] = None,
    vendor_properties: Optional[Dict[str, Any]] = None,
) -> None:
    source_obj = yaml.safe_load(source_file.read_text(**fopen_kwargs))

    if vendor_properties:
        for key, value in vendor_properties.items():
            source_obj[key] = value

    for patch_file in patch_files:
        patch_obj = yaml.safe_load(patch_file.read_text(**fopen_kwargs))
        source_obj = jsonpatchplus.patch(doc=source_obj, patches=patch_obj, loader=None)
        logging.info(
            "[ok] applied patch '%s' to '%s'",
            patch_file.name,
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )

    destination_file.parent.mkdir(**mkdir_kwargs)
    destination_file.write_text(yaml.safe_dump(source_obj, **safe_dump_kwargs))


def timestamp(destination_file: Path, destination_dir: Optional[Path] = None) -> None:
    destination_file.write_text(datetime.datetime.utcnow().isoformat())
    logging.info(
        "[ok] updated timestamp '%s'",
        destination_file.name
        if destination_dir is None
        else destination_file.relative_to(destination_dir),
    )


# noinspection PyBroadException
def try_get_git_hash(path: Path) -> Optional[str]:
    owd = getcwd()
    chdir(str(path))

    try:
        result = (
            check_output(["git", "rev-parse", "HEAD"]).decode(encoding="utf-8").strip()
        )
    except Exception:
        result = None

    chdir(owd)
    return result


if __name__ == "__main__":
    run()
