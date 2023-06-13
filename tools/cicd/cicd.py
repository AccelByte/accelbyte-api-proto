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

default_template_file = "templates/proto.j2"
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
@click.option("--template_file")
def run(
    template_dir: Path,
    source_dir: Path,
    destination_dir: Path,
    template_file: Optional[str] = None,
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
            template_file=template_file,
        )

        # 3.b. Convert to .mc.properties
        if success_proto:
            dst_proto = dst.parent / f"{dst.stem}.mc.properties"
            convert_to_message_class_map_properties(
                source_file=src_patch,
                destination_file=dst_proto,
                source_dir=destination_dir,
                destination_dir=destination_dir,
            )

        # 3.c. Convert to .sc.properties
        if success_proto:
            dst_proto = dst.parent / f"{dst.stem}.sc.properties"
            convert_to_service_class_map_properties(
                source_file=src_patch,
                destination_file=dst_proto,
                source_dir=destination_dir,
                destination_dir=destination_dir,
            )

    # 4.a Merge .mc.properties files
    dst_mc_properties = destination_dir / "topicMessageToMessageClassMapping.properties"
    merge_files(
        source_dir=destination_dir,
        destination_file=dst_mc_properties,
        file_extension=".mc.properties",
        prefix=header,
        destination_dir=destination_dir,
    )

    # 4.b Merge .sc.properties files
    dst_mc_properties = destination_dir / "topicToServiceClassMapping.properties"
    merge_files(
        source_dir=destination_dir,
        destination_file=dst_mc_properties,
        file_extension=".sc.properties",
        prefix=header,
        destination_dir=destination_dir,
    )

    # 5. Add TIMESTAMP
    timestamp_file = destination_dir / "TIMESTAMP"
    timestamp(destination_file=timestamp_file, destination_dir=destination_dir)


# noinspection PyBroadException, PyShadowingBuiltins
def convert_to_message_class_map_properties(
    source_file: Path,
    destination_file: Path,
    source_dir: Optional[Path] = None,
    destination_dir: Optional[Path] = None,
) -> bool:
    if not all(imports.__dict__.values()):
        logging.warning(
            "conversion dependencies missing, skipping '%s'!",
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
        return False

    try:
        input = imports.processor_class()(str(source_file))
        imports.render(
            input=input,
            template="templates/message-message_class-map-properties.j2",
            output=destination_file,
            **render_kwargs,
        )
        logging.info(
            "converted from '%s' to '%s'",
            source_file.name
            if source_dir is None
            else source_file.relative_to(source_dir),
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
    except Exception as error:
        logging.warning(
            "conversion failed due to [%s]: %s, skipping '%s'!",
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
) -> bool:
    if not all(imports.__dict__.values()):
        logging.warning(
            "conversion dependencies missing, skipping '%s'!",
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
        return False

    try:
        input = imports.processor_class()(str(source_file))
        imports.render(
            input=input,
            template="templates/topic-service_class-map-properties.j2",
            output=destination_file,
            **render_kwargs,
        )
        logging.info(
            "converted from '%s' to '%s'",
            source_file.name
            if source_dir is None
            else source_file.relative_to(source_dir),
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
    except Exception as error:
        logging.warning(
            "conversion failed due to [%s]: %s, skipping '%s'!",
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
    template_file: Optional[str] = None,
) -> bool:
    if not all(imports.__dict__.values()):
        logging.warning(
            "conversion dependencies missing, skipping '%s'!",
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
        )
        return False

    try:
        input = imports.processor_class()(str(source_file))
        imports.render(
            input=input,
            template=template_file or default_template_file,
            output=destination_file,
            **render_kwargs,
        )
        logging.info(
            "converted from '%s' to '%s' (%s)",
            source_file.name
            if source_dir is None
            else source_file.relative_to(source_dir),
            destination_file.name
            if destination_dir is None
            else destination_file.relative_to(destination_dir),
            template_file,
        )
    except Exception as error:
        logging.warning(
            "conversion failed due to [%s]: %s, skipping '%s'!",
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
        "copied from '%s' to '%s'",
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
        logging.info(
            "appended contents of '%s' to '%s'",
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
            "applied patch '%s' to '%s'",
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
        "updated timestamp '%s'",
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
