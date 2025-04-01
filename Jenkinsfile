pipeline {
    agent any

    environment {
        VERSION = GIT_COMMIT.take(7)
    }

    stages {
        stage('build') {
            parallel {
                stage('daemon') {
                    stages {
                        stage('image') {
                            steps {
                                dir('daemon') {
                                    sh 'make image -e VERSION=${VERSION}'
                                }
                            }
                        }
                        stage('test') {
                            steps {
                                dir('daemon') {
                                    sh 'make test -e VERSION=${VERSION}'
                                }
                            }
                        }
                        stage('lint') {
                            steps {
                                dir('daemon') {
                                    sh 'make lint -e VERSION=${VERSION}'
                                }
                            }
                        }
                    }
                }
                stage('module') {
                    stages {
                        stage('setup') {
                            steps {
                                sh 'make setup'
                            }
                        }
                    }
                }
            }
        }
        stage('push') {
            when {
                branch "main"
            }
            stages {
                stage('hash') {
                    parallel {
                        stage('daemon') {
                            steps {
                                dir('daemon') {
                                    sh 'make push -e VERSION=${VERSION}'
                                }
                            }
                        }
                    }
                }
                stage('semver') {
                    steps {
                        sh 'make semver -e VERSION=${VERSION}'
                    }
                }
            }
        }
    }
}
