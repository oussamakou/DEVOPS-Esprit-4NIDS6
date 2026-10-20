package tn.esprit.studentmanagement;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.ActiveProfiles;
import tn.esprit.studentmanagement.entities.Student;

import static org.assertj.core.api.Assertions.assertThat;

@ActiveProfiles("test")
@AutoConfigureObservability
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "management.server.port=0")
class ApiAndManagementTest {
    @Autowired
    private TestRestTemplate http;

    @LocalManagementPort
    private int managementPort;

    @LocalServerPort
    private int applicationPort;

    private String api(String path) {
        return "http://localhost:" + applicationPort + "/student" + path;
    }

    @Test
    void createsAndReadsStudentThroughHttp() {
        Student student = new Student();
        student.setFirstName("Ada");
        student.setLastName("Lovelace");
        student.setEmail("ada@example.test");
        var created = http.postForEntity(api("/students/createStudent"), student, Student.class);
        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(created.getBody()).isNotNull();
        Long id = created.getBody().getIdStudent();
        assertThat(id).isPositive();
        var loaded = http.getForEntity(api("/students/getStudent/" + id), Student.class);
        assertThat(loaded.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(loaded.getBody().getEmail()).isEqualTo("ada@example.test");
        http.delete(api("/students/deleteStudent/" + id));
    }

    @Test
    void readinessIncludesDatabaseAndLivenessIsAvailable() {
        for (String group : new String[]{"readiness", "liveness"}) {
            var response = http.getForEntity("http://localhost:" + managementPort
                    + "/actuator/health/" + group, String.class);
            assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
            assertThat(response.getBody()).contains("\"status\":\"UP\"");
        }
    }

    @Test
    void prometheusIsAvailableOnlyOnManagementPort() {
        var metrics = http.getForEntity("http://localhost:" + managementPort
                + "/actuator/prometheus", String.class);
        assertThat(metrics.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(metrics.getBody()).contains("jvm_memory_used_bytes", "application=\"student-management\"");
        assertThat(http.getForEntity(api("/actuator/prometheus"), String.class).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }
}
