import sqlite3

# Connect to SQLite
connection = sqlite3.connect("student.db")

# Create cursor
cursor = connection.cursor()

# Create the table (if it doesn't exist)
table_info = """
CREATE TABLE IF NOT EXISTS STUDENT(
    NAME VARCHAR(25),
    CLASS VARCHAR(25),
    SECTION VARCHAR(25),
    MARKS INT
)
"""
cursor.execute(table_info)

# Insert multiple records efficiently
students = [
    ('Krish', 'Data Science', 'A', 90),
    ('John', 'Data Science', 'B', 100),
    ('Mukesh', 'Data Science', 'A', 86),
    ('Jacob', 'DEVOPS', 'A', 50),
    ('Dipesh', 'DEVOPS', 'A', 35)
]

cursor.executemany("INSERT INTO STUDENT VALUES (?, ?, ?, ?)", students)

# Display all records
print("The inserted records are:")
for row in cursor.execute("SELECT * FROM STUDENT"):
    print(row)

# Commit and close
connection.commit()
connection.close()
