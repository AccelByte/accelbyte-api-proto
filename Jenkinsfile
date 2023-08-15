library(
  identifier: 'jenkins-shared-library@master',
  retriever: modernSCM(
    [
      $class: 'GitSCMSource',
      remote: 'https://github.com/dhanarab/jenkins-pipeline-library.git'
    ]
  )
)

bitbucketHttpsCredentials = "bitbucket-build-extend-https"
bitbucketCredentialsSsh = "bitbucket-build-extend-ssh"

bitbucketPayload = null
bitbucketCommitHref = null

def getCommitMessageInRange(startCommitHash, endCommitHash) {
  shScript = "git log --pretty=format:'%s' " + startCommitHash + "..." +  endCommitHash
  return sh(returnStdout: true, script: shScript)
}

def hasBreakingChangesSymbol(commitMessages) {
  if (commitMessages =~ "(feat|fix|docs|chore)(\\(.*\\))?!:") {
      return true
  }
  return false
}

pipeline {
  agent none
  stages {
    stage('Prepare') {
      agent {
        label "master"
      }
      steps {
        script {
          if (env.BITBUCKET_PAYLOAD) {
            bitbucketPayload = readJSON text: env.BITBUCKET_PAYLOAD
            if (bitbucketPayload.pullrequest) {
              bitbucketCommitHref = bitbucketPayload.pullrequest.source.commit.links.self.href
            }
          }
          if (bitbucketCommitHref) {
            bitbucket.setBuildStatus(bitbucketHttpsCredentials, bitbucketCommitHref, "INPROGRESS", env.JOB_NAME.take(30), "${env.JOB_NAME}-${env.BUILD_NUMBER}", "Jenkins", "${env.BUILD_URL}console")
          }
        }
      }
    }
    stage('Lint') {
        agent {
            label "justice-codegen-sdk"
        }
        steps {
            sh "make lint"
        }
    }
    stage('Check Proto Breaking Changes') {
      agent {
        label "justice-codegen-sdk"
      }
      steps {
        script {
          commitMessages = getCommitMessageInRange(
            env.BITBUCKET_PULL_REQUEST_LATEST_COMMIT_FROM_TARGET_BRANCH,
            env.BITBUCKET_PULL_REQUEST_LATEST_COMMIT_FROM_SOURCE_BRANCH
          )
          echo 'Commits from pull request'
          echo commitMessages
          if (hasBreakingChangesSymbol(commitMessages)) {
            echo 'This pull request has ! symbol, skip breaking changes checking'
          } else {
            sh 'make breaking -s'
          }
        }
      }
    }
    stage('Check Proto Governance') {
      agent {
        label "justice-codegen-sdk"
      }
      steps {
        script {
          sh 'make governance'
        }
      }
    }
  }
  post {
    success {
      script {
        if (bitbucketCommitHref) {
          bitbucket.setBuildStatus(bitbucketHttpsCredentials, bitbucketCommitHref, "SUCCESSFUL", env.JOB_NAME.take(30), "${env.JOB_NAME}-${env.BUILD_NUMBER}", "Jenkins", "${env.BUILD_URL}console")
        }
      }
    }
    failure {
      script {
        if (bitbucketCommitHref) {
          bitbucket.setBuildStatus(bitbucketHttpsCredentials, bitbucketCommitHref, "FAILED", env.JOB_NAME.take(30), "${env.JOB_NAME}-${env.BUILD_NUMBER}", "Jenkins", "${env.BUILD_URL}console")
        }
      }
    }
  }
}
