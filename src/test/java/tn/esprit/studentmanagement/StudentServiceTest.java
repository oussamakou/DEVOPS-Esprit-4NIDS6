package tn.esprit.studentmanagement;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import tn.esprit.studentmanagement.entities.Student;
import tn.esprit.studentmanagement.services.StudentService;

import java.util.List;

@SpringBootTest
@ActiveProfiles("test")
public class StudentServiceTest {

    @Autowired
    private StudentService studentService;

    @Test
    public void testAddStudent() {
        Student student = new Student();
        student.setFirstName("John");
        student.setLastName("Doe");
        student.setEmail("john.doe@esprit.tn");

        Student savedStudent = studentService.saveStudent(student);

        Assertions.assertNotNull(savedStudent.getIdStudent());
        Assertions.assertEquals("John", savedStudent.getFirstName());
    }

    @Test
    public void testGetAllStudents() {
        List<Student> students = studentService.getAllStudents();
        Assertions.assertNotNull(students);
    }
}
