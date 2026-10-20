# syntax=docker/dockerfile:1
# CI uses its tested JAR. The local target builds from source for Docker Compose.
FROM maven:3.9.11-eclipse-temurin-17 AS builder
WORKDIR /build
COPY pom.xml ./
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp dependency:go-offline
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp package -DskipTests

FROM eclipse-temurin:17-jre-alpine AS runtime
RUN apk upgrade --no-cache && addgroup -g 10001 app && adduser -D -u 10001 -G app app
WORKDIR /app
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -XX:+ExitOnOutOfMemoryError"
USER 10001:10001
EXPOSE 8089 9090
ENTRYPOINT ["java", "-jar", "/app/app.jar"]

FROM runtime AS ci
COPY --chown=10001:10001 target/student-management-0.0.1-SNAPSHOT.jar /app/app.jar

FROM runtime AS local
COPY --from=builder --chown=10001:10001 /build/target/student-management-0.0.1-SNAPSHOT.jar /app/app.jar
