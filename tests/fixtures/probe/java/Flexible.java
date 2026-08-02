package demo;

class Account {
    private final String owner;
    private final long balanceCents;

    Account(String owner, long balanceCents) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner required");
        }
        if (balanceCents < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        this.owner = owner;
        this.balanceCents = balanceCents;
    }
}
