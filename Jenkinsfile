pipeline {
    agent any

    environment {
        VERSION = GIT_COMMIT.take(7)
    }

    stages {
        stage('build') {
            parallel {
                stage('api') {
                    stages {
                        stage('image') {
                            steps {
                                dir('api') {
                                    sh 'make image -e VERSION=${VERSION}'
                                }
                            }
                        }
                        stage('ddl') {
                            steps {
                                dir('api') {
                                    sh 'make ddl -e VERSION=${VERSION}'
                                }
                            }
                        }
                        stage('test') {
                            steps {
                                dir('api') {
                                    sh 'make test -e VERSION=${VERSION}'
                                }
                            }
                        }
                        stage('lint') {
                            steps {
                                dir('api') {
                                    sh 'make lint -e VERSION=${VERSION}'
                                }
                            }
                        }
                    }
                }
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
                stage('cron') {
                    stages {
                        stage('image') {
                            steps {
                                dir('cron') {
                                    sh 'make image -e VERSION=${VERSION}'
                                }
                            }
                        }
                        stage('test') {
                            steps {
                                dir('cron') {
                                    sh 'make test -e VERSION=${VERSION}'
                                }
                            }
                        }
                        stage('lint') {
                            steps {
                                dir('cron') {
                                    sh 'make lint -e VERSION=${VERSION}'
                                }
                            }
                        }
                    }
                }
                stage('gui') {
                    stages {
                        stage('image') {
                            steps {
                                dir('gui') {
                                    sh 'make image -e VERSION=${VERSION}'
                                }
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
            parallel {
                stage('api') {
                    steps {
                        dir('api') {
                            sh 'make push -e VERSION=${VERSION}'
                        }
                    }
                }
                stage('daemon') {
                    steps {
                        dir('daemon') {
                            sh 'make push -e VERSION=${VERSION}'
                        }
                    }
                }
                stage('cron') {
                    steps {
                        dir('cron') {
                            sh 'make push -e VERSION=${VERSION}'
                        }
                    }
                }
                stage('gui') {
                    steps {
                        dir('gui') {
                            sh 'make push -e VERSION=${VERSION}'
                        }
                    }
                }
            }
        }
    }
}
