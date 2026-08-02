package demo;

sealed interface Shape permits Circle, Square, Triangle {}
record Circle(double radius) implements Shape {}
record Square(double side) implements Shape {}
record Triangle(double base, double height) implements Shape {}

final class AreaCalculator {
    double area(Shape shape) {
        return switch (shape) {
            case Circle circle when circle.radius() > 100 -> Math.PI * circle.radius() * circle.radius() * 2;
            case Circle circle -> Math.PI * circle.radius() * circle.radius();
            case Square square when square.side() <= 0 -> 0d;
            case Square square -> square.side() * square.side();
            case Triangle triangle -> 0.5d * triangle.base() * triangle.height();
        };
    }
}
