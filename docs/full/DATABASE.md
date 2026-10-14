# ������ ����� SQLite

������ `299d311`. ���� �������� SCHEMA �� `app.py`, `eve_harness.py`, `eve_commands.py`, ��� ����������� � ���������������� ����. ��������� legacy-����� ����� ��������� �� ����.

## app.py

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_date TEXT NOT NULL,
    text TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT '������',
    scope TEXT NOT NULL DEFAULT 'planner',
    start_time TEXT,
    end_time TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(task_date);

CREATE TABLE IF NOT EXISTS weekly_goals (
    week_monday TEXT PRIMARY KEY,
    text TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    note_date TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color TEXT NOT NULL DEFAULT '#4D67FF',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monthly_priorities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    text TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monthly_priorities_month ON monthly_priorities(month, sort_order, id);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    category TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);

CREATE TABLE IF NOT EXISTS utility_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    account_number TEXT NOT NULL DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS utility_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES utility_accounts(id) ON DELETE CASCADE,
    billing_month TEXT NOT NULL,
    due_date TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    status TEXT NOT NULL CHECK (status IN ('pending', 'paid')) DEFAULT 'pending',
    note TEXT NOT NULL DEFAULT '',
    paid_at TEXT,
    paid_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, billing_month)
);
CREATE INDEX IF NOT EXISTS idx_utility_payments_month ON utility_payments(billing_month);

CREATE TABLE IF NOT EXISTS utility_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES utility_accounts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, name)
);
CREATE INDEX IF NOT EXISTS idx_utility_services_account ON utility_services(account_id, archived, id);

CREATE TABLE IF NOT EXISTS utility_meter_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES utility_accounts(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL REFERENCES utility_services(id) ON DELETE CASCADE,
    reading_value REAL NOT NULL CHECK (reading_value >= 0),
    reading_date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(service_id, reading_date)
);
CREATE INDEX IF NOT EXISTS idx_utility_meter_readings_service ON utility_meter_readings(service_id, reading_date DESC);

CREATE TABLE IF NOT EXISTS utility_meter_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES utility_accounts(id) ON DELETE CASCADE,
    submission_month TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    UNIQUE(account_id, submission_month)
);

CREATE TABLE IF NOT EXISTS utility_payment_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES utility_payments(id) ON DELETE CASCADE,
    service_id INTEGER REFERENCES utility_services(id) ON DELETE SET NULL,
    service_name TEXT NOT NULL,
    tariff_minor INTEGER,
    previous_reading REAL,
    current_reading REAL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_utility_payment_items_payment ON utility_payment_items(payment_id, id);

CREATE TABLE IF NOT EXISTS utility_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS savings_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    goal_minor INTEGER NOT NULL DEFAULT 0 CHECK (goal_minor >= 0),
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS savings_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES savings_categories(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('initial', 'deposit', 'withdrawal')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    operation_date TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_savings_operations_category ON savings_operations(category_id, operation_date DESC, id DESC);

CREATE TABLE IF NOT EXISTS savings_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL UNIQUE REFERENCES savings_categories(id) ON DELETE CASCADE,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly')) DEFAULT 'daily',
    schedule_days TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
    target_per_week INTEGER NOT NULL DEFAULT 7,
    color TEXT NOT NULL DEFAULT '#ff2290',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS habit_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    entry_date TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    UNIQUE(habit_id, entry_date)
);
CREATE INDEX IF NOT EXISTS idx_habit_entries_date ON habit_entries(entry_date);

CREATE TABLE IF NOT EXISTS mood_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL UNIQUE,
    score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
    label TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mood_entries_date ON mood_entries(entry_date);

CREATE TABLE IF NOT EXISTS assistant_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assistant_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_history_id ON assistant_history(id);

CREATE TABLE IF NOT EXISTS assistant_chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_chat_history_id ON assistant_chat_history(id);

CREATE TABLE IF NOT EXISTS assistant_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    normalized_fact TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### ������������� ������ ����

```python
def ensure_legacy_columns(conn: sqlite3.Connection) -> None:
    """Bring databases created by the first version up to the current schema."""
    migrations = (
        ("tasks", "section", "TEXT NOT NULL DEFAULT '������'"),
        ("tasks", "scope", "TEXT NOT NULL DEFAULT 'planner'"),
        ("notes", "pinned", "INTEGER NOT NULL DEFAULT 0"),
        ("utility_accounts", "address", "TEXT NOT NULL DEFAULT ''"),
        ("utility_payments", "paid_date", "TEXT"),
    )
    for table, column, definition in migrations:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_scope_date ON tasks(scope, task_date)")
    conn.commit()
```

## eve_harness.py

```sql
CREATE TABLE IF NOT EXISTS assistant_task_proposals (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
```

## eve_commands.py

```sql
CREATE TABLE IF NOT EXISTS assistant_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phrase TEXT NOT NULL,
    normalized_phrase TEXT NOT NULL UNIQUE,
    template TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('command','prompt')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
```

## ������� �������������

����� ��������� ���������, �� �������� ���������������� ������. ������ � `amount_minor` �������� ������ ������������ ���������. ������� �� ���������� ��������� ���������� REAL. ���������� �� ��������� ��������� �� ������������� �������� � ������ ��������; ��� �� ������ � ��� SQL-�������. ��������� ����� ���� ������� ������ ��� �������� ����������.
