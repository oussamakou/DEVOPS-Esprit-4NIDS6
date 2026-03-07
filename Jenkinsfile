pipeline {
    agent any

    environment {
        // 🚨 CHANGE THIS to your Docker Hub username
        DOCKER_HUB_USER = "oussk" 
        IMAGE_NAME = "student-management"
        DOCKER_CREDENTIALS_ID = 'docker-hub-creds'
    }

    stages {
        stage('Prepare') {
            steps {
                // Ensure the Maven wrapper is executable
                sh 'chmod +x mvnw'
                echo "✅ Maven wrapper prepared"
            }
        }

        stage('Build & Test') {
            steps {
                // We remove -DskipTests so JaCoCo can generate the coverage report
                sh './mvnw clean package' 
            }
        }

        stage('SonarQube Analysis') {
            steps {
                // 'sonar-server' must be configured in Jenkins Global Config
                withSonarQubeEnv('sonar-server') {
                    sh './mvnw sonar:sonar'
                }
            }
        }

        stage('Docker Build & Push') {
            steps {
                script {
                    docker.withRegistry('', DOCKER_CREDENTIALS_ID) {
                        def appImage = docker.build("${DOCKER_HUB_USER}/${IMAGE_NAME}:${BUILD_NUMBER}")
                        appImage.push()
                        appImage.push('latest')
                    }
                }
            }
        }

        stage('Update K8s Manifest') {
            steps {
                // This replaces the placeholder IMAGE_WITH_TAG in the k8s file with the actual image
                sh "sed -i 's|IMAGE_PLACEHOLDER|${DOCKER_HUB_USER}/${IMAGE_NAME}:${BUILD_NUMBER}|g' k8s/deployment.yaml"
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                sh 'kubectl apply -f k8s/'
                echo "Deployment triggered on Minikube"
            }
        }
    }
}
