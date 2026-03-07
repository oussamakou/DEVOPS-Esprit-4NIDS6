# 📂 DevOps Journey: Student Management Deployment

This document logs the step-by-step progress of the deployment phases. Store screenshots in the `./screenshots` folder.

---

## 🏗️ Phase 1: Infrastructure & Jenkins Setup

**Goal:** Get the Ubuntu server running and install the core automation tools.

### Steps Taken:
1.  **Vagrant Up:** Spun up the Ubuntu Jammy64 VM using the `Vagrantfile`.
2.  **Docker Installation:** Installed Docker on the VM to host Jenkins and other services.
3.  **Jenkins via Docker:** Ran Jenkins as a container mounting the Docker socket for "Docker-out-of-Docker" capabilities.
4.  **Initial Setup:** Unlocked Jenkins using the admin password from logs and started plugin installation.

### 📸 Screenshots to Capture:
- [X] **Screenshot 1:** `screenshot1_getting_started.png` - Plugin installation progress (The image you shared).
- [ ] **Screenshot 2:** `screenshot2_dashboard.png` - The main screen after setup is finished.
- [ ] **Screenshot 3:** `screenshot3_plugins.png` - Showing `Docker Pipeline` and `SonarQube Scanner` installed.

---

## 🐋 Phase 2: Project Dockerization

**Goal:** Package the Spring Boot app into a deployable container.

### Steps Taken:
1.  **Dockerfile Creation:** Created a multi-stage `Dockerfile` (Maven build + JRE runtime).
2.  **Networking Fix:** Updated `application.properties` to connect to `mysql` instead of `localhost`.
3.  **Local Test:** Ran `docker-compose up -d` to verify the app and DB talk to each other.

### 📸 Screenshots to Capture:
- [ ] **Screenshot 4:** `screenshot4_docker_ps.png` - Terminal showing `docker ps` with both the app and mysql containers running.
- [ ] **Screenshot 5:** `screenshot5_swagger.png` - Browser showing the Swagger UI at `http://192.168.50.4:8089/student/swagger-ui/index.html`.

---

## 🤖 Phase 3: CI/CD Pipeline (Jenkins & SonarQube)

**Goal:** Automate the build and quality check process.

### Steps Taken:
1.  **SonarQube Up:** Started SonarQube container on port 9000.
2.  **Jenkins Credentials:** Added `docker-hub-creds` and `sonar-token` to Jenkins.
3.  **Create Pipeline Job:** 
    *   New Item > Pipeline > `student-management`.
    *   Set **Pipeline script from SCM**.
    *   Configured Git URL and GitHub Credentials.
    *   Set script path to `Jenkinsfile`.

### 📸 Screenshots to Capture:
- [ ] **Screenshot 6:** `screenshot6_sonarqube.png` - SonarQube dashboard showing the first successful scan of the project.
- [ ] **Screenshot 7:** `screenshot7_stage_view.png` - Jenkins Pipeline "Stage View" - Showing all green blocks from Checkout to Build.

---

## ☸️ Phase 4: Kubernetes Deployment (Minikube)

**Goal:** Deploy the app to a production-like cluster.

### Steps Taken:
1.  **Minikube Start:** Initialized the cluster on the VM.
2.  **K8s Manifests:** Created deployment, service, and secret files in the `k8s/` folder.
3.  **Final Deployment:** Jenkins pipeline triggers `kubectl apply` to roll out the app.

### 📸 Screenshots to Capture:
- [ ] **Screenshot 8:** `screenshot8_kubectl_pods.png` - Terminal showing `kubectl get pods` with the app and mysql pods in "Running" state.
- [ ] **Screenshot 9:** `screenshot9_k8s_service.png` - Browser showing the app running through the NodePort `http://192.168.50.4:30089/student/...`.

---

## 🧪 Lab Practice: Manual K8s Objects (Command-line only)

**Goal:** Create a standalone Nginx Pod and expose it without using YAML files (as requested by the professor).

### 🛠️ Execution Steps (Commands):
1.  **Create Pod:** Run `kubectl run oussa-nginx --image=nginx`
2.  **Expose Service:** Run `kubectl expose pod oussa-nginx --type=NodePort --port=80`
3.  **Verify:** Run `kubectl get pods,svc` to see the status and the assigned NodePort.
4.  **Access:** Run `minikube service oussa-nginx --url` to get the final browser link.

### 📸 Screenshots to Capture:
- [ ] **Screenshot 10:** `screenshot10_nginx_lab.png` - Terminal showing the success of the two commands and the service URL.
- [ ] **Screenshot 11:** `screenshot11_nginx_browser.png` - The standard "Welcome to nginx!" page in your browser.

---

## 🏁 Final Success
- [ ] Entire pipeline runs automatically on `git push`.
- [ ] App is reachable via the Kubernetes Service.
