library(
    identifier: 'jenkins-shared-library@master',
    retriever: modernSCM(
        [
            $class: 'GitSCMSource',
            remote: 'https://github.com/dhanarab/jenkins-pipeline-library.git'
        ]
    )
)

bitbucketNamespace = "accelbyte"
bitbucketCredentialsHttps = "bitbucket-build-extend-https"
bitbucketCredentialsSsh = "bitbucket-build-extend-ssh"

repoName = "grpc-plugin-proto"
repoPath = null
repoBranchName = null
repoCommitHash = null
repoCommitHashShort = null
repoCommitMessage = null

specRepoName = "justice-api-specification"
specRepoPath = null
specRepoCommitHash = null

codegenRepoName = "justice-codegen-sdk-v2"
codegenRepoPath = null
codegenRepoCommitHash = null

slackActivityChannel = "#activity-extend-engineering"

pipeline {
    agent {
        label "justice-codegen-sdk"
    }
    stages {
        stage("Prepare") {
            steps {
                script {
                    repoPath = "${env.WORKSPACE}/${repoName}"
                    specRepoPath = "${env.WORKSPACE}/${specRepoName}"
                    codegenRepoPath = "${env.WORKSPACE}/${codegenRepoName}"

                    sh "rm -rf ${specRepoPath}"
                    sh "rm -rf ${codegenRepoName}"

                    sshagent(credentials: [bitbucketCredentialsSsh]) {
                        sh "git clone --depth 1 git@bitbucket.org:${bitbucketNamespace}/${specRepoName}.git ${specRepoPath}"
                        sh "git clone --depth 1 git@bitbucket.org:${bitbucketNamespace}/${codegenRepoName}.git ${codegenRepoPath}"
                    }

                    dir(specRepoPath) {
                        specRepoCommitHash = sh(returnStdout: true, script: "git rev-parse HEAD").trim()
                    }
                    dir(codegenRepoPath) {
                        codegenRepoCommitHash = sh(returnStdout: true, script: "git rev-parse HEAD").trim()
                    }
                }
            }
        }

        stage("Run") {
            steps {
                dir("tools/cicd") {
                    sh "make dbuild drun CODEGEN_SDK_PATH=${codegenRepoPath} SPEC_PATH=${specRepoPath}"
                }
            }
        }

        stage("Update") {
            steps {
                script {
                    if (sh(script: "git add asyncapi && git status --porcelain asyncapi", returnStatus: true) == 0) {
                        zip(zipFile: "asyncapi.zip", dir: "asyncapi/", overwrite: true, archive: true)

                        repoBranchName = sh(script: "echo ${env.GIT_BRANCH} | grep -oP '(?<=origin/).+'", returnStdout: true).trim()

                        sshagent(credentials: [bitbucketCredentialsSsh]) {
                            sh "git commit -m \"chore(proto): update proto files \$(cat asyncapi/TIMESTAMP)\" && git push origin HEAD:${repoBranchName}"
                        }

                        repoCommitHash = git.getCommitHash()
                        repoCommitHashShort = git.getCommitHashShort()
                        repoCommitMessage = git.getCommitMessage()

                        message = """
                            :white_check_mark: <${env.BUILD_URL}|${env.JOB_NAME}-${env.BUILD_NUMBER}> *proto files updated*

                            |*${repoName}:*
                            |<https://bitbucket.org/accelbyte/${repoName}/commits/${repoCommitHash}|${repoBranchName} ${repoCommitHashShort}>
                            |${repoCommitMessage}

                            |*Artifacts:*
                            |<${env.BUILD_URL}artifact|Build Artifacts>

                            |""".stripMargin()

                        slackSend(channel: "${slackActivityChannel}", color: '#36B37E', message: message)
                    }
                }
            }
        }
    }
    post {
        failure {
            script {
                message = """
                    :no_entry: <${env.BUILD_URL}|${env.JOB_NAME}-${env.BUILD_NUMBER}> *proto files update failed*

                    |""".stripMargin()

                slackSend(channel: "${slackActivityChannel}", color: '#FF0000', message: message)
            }
        }
    }
}