import module java.base;

void main() {
    var orders = List.of("a", "b", "c");
    for (var order : orders) {
        if (order.isEmpty()) continue;
        if (order.length() > 2 && order.startsWith("a")) {
            IO.println(order);
        } else if (order.length() > 1 || order.endsWith("c")) {
            IO.println("short " + order);
        }
    }
}
