-- SQL Copilot Agent — demo database schema + seed data (reference).
--
-- This file documents the schema the agent works against and reproduces the
-- bundled demo data. It is the same structure that `database.py` creates and
-- seeds automatically at runtime — `database.py` is the source of truth; this
-- file is a human-readable reference and a way to rebuild the DB by hand:
--
--     sqlite3 demo.db < schema.sql
--
-- Note the `is_deleted` soft-delete flag on customers, products, and orders:
-- records are never hard-deleted; they are marked is_deleted = 1 instead.

PRAGMA foreign_keys = ON;

-- --------------------------------------------------------------------------- --
-- Schema
-- --------------------------------------------------------------------------- --
CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    city        TEXT    NOT NULL,
    signup_date TEXT    NOT NULL,              -- ISO date (YYYY-MM-DD)
    is_deleted  INTEGER NOT NULL DEFAULT 0     -- soft-delete flag (0 = active)
);

CREATE TABLE products (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    category   TEXT    NOT NULL,
    price      REAL    NOT NULL,               -- unit price in INR
    is_deleted INTEGER NOT NULL DEFAULT 0      -- soft-delete flag (0 = active)
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date  TEXT    NOT NULL,              -- ISO date (YYYY-MM-DD)
    status      TEXT    NOT NULL,              -- placed | shipped | delivered | cancelled
    is_deleted  INTEGER NOT NULL DEFAULT 0     -- soft-delete flag (0 = active)
);

CREATE TABLE order_items (
    id         INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL
);

-- --------------------------------------------------------------------------- --
-- Seed data
-- --------------------------------------------------------------------------- --
INSERT INTO customers (id, name, city, signup_date) VALUES
    (1, 'Aarav Sharma',  'Bengaluru', '2024-01-12'),
    (2, 'Diya Nair',     'Mumbai',    '2024-02-03'),
    (3, 'Vikram Reddy',  'Bengaluru', '2024-02-28'),
    (4, 'Meera Iyer',    'Chennai',   '2024-03-15'),
    (5, 'Rohan Gupta',   'Delhi',     '2024-04-01'),
    (6, 'Ananya Rao',    'Bengaluru', '2024-05-22'),
    (7, 'Karthik Menon', 'Kochi',     '2024-06-10'),
    (8, 'Sana Khan',     'Hyderabad', '2024-07-19');

INSERT INTO products (id, name, category, price) VALUES
    (1, 'Mechanical Keyboard',         'Peripherals', 6499.0),
    (2, 'USB-C Hub',                   'Peripherals', 2999.0),
    (3, '27-inch Monitor',             'Displays',    18999.0),
    (4, 'Noise-Cancelling Headphones', 'Audio',       12499.0),
    (5, 'Webcam 1080p',                'Peripherals', 3499.0),
    (6, 'Laptop Stand',                'Accessories', 1799.0),
    (7, 'Ergonomic Mouse',             'Peripherals', 2499.0),
    (8, 'Standing Desk',               'Furniture',   24999.0);

INSERT INTO orders (id, customer_id, order_date, status) VALUES
    (1,  1, '2024-06-01', 'delivered'),
    (2,  1, '2024-08-14', 'delivered'),
    (3,  2, '2024-06-20', 'shipped'),
    (4,  3, '2024-07-02', 'delivered'),
    (5,  3, '2024-09-11', 'cancelled'),
    (6,  4, '2024-07-25', 'delivered'),
    (7,  5, '2024-08-05', 'placed'),
    (8,  6, '2024-09-01', 'delivered'),
    (9,  6, '2024-09-30', 'shipped'),
    (10, 7, '2024-10-02', 'delivered'),
    (11, 8, '2024-10-10', 'placed'),
    (12, 1, '2024-10-18', 'shipped');

INSERT INTO order_items (id, order_id, product_id, quantity) VALUES
    (1,  1,  1, 1),
    (2,  1,  2, 2),
    (3,  2,  3, 1),
    (4,  3,  4, 1),
    (5,  4,  1, 1),
    (6,  4,  7, 1),
    (7,  5,  8, 1),
    (8,  6,  3, 2),
    (9,  7,  5, 1),
    (10, 8,  4, 1),
    (11, 8,  6, 1),
    (12, 9,  2, 1),
    (13, 10, 1, 1),
    (14, 10, 7, 2),
    (15, 11, 8, 1),
    (16, 12, 3, 1),
    (17, 12, 6, 1);
