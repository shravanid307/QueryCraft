from pathlib import Path
import sqlite3


def extract_schema(db_path):
    db_path = Path(db_path)

    if not db_path.is_absolute():
        db_path = Path(__file__).resolve().parent.parent / db_path

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # 1. Extract tables, columns, and primary keys
        cur.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%';
        """)

        table_names = [row[0] for row in cur.fetchall()]
        schema = {}

        for table_name in table_names:
            cur.execute(f'PRAGMA table_info("{table_name}")')
            columns = cur.fetchall()

            schema[table_name] = {
                "columns": {},
                "primary_key": None
            }

            for column in columns:
                column_name = column[1]
                data_type = column[2]
                is_primary_key = column[5]

                schema[table_name]["columns"][column_name] = data_type

                if is_primary_key:
                    schema[table_name]["primary_key"] = column_name

        # 2. Detect declared foreign keys
        relationships = []

        for table_name in table_names:
            cur.execute(f'PRAGMA foreign_key_list("{table_name}")')

            for fk in cur.fetchall():
                relationships.append({
                    "from_table": table_name,
                    "from_column": fk[3],
                    "to_table": fk[2],
                    "to_column": fk[4],
                    "source": "declared"
                })

        # 3. Infer relationships not already declared
        existing = {
            (
                r["from_table"], r["from_column"],
                r["to_table"], r["to_column"]
            )
            for r in relationships
        }

        for table_name, table_info in schema.items():
            for column_name in table_info["columns"]:

                if column_name == table_info["primary_key"]:
                    continue

                if not column_name.endswith("_id"):
                    continue

                base_name = column_name[:-3]
                possible_tables = [base_name, base_name + "s"]

                for target_table in possible_tables:
                    if target_table not in schema:
                        continue

                    if schema[target_table]["primary_key"] != column_name:
                        continue

                    key = (
                        table_name, column_name,
                        target_table, column_name
                    )

                    if key not in existing:
                        relationships.append({
                            "from_table": table_name,
                            "from_column": column_name,
                            "to_table": target_table,
                            "to_column": column_name,
                            "source": "inferred"
                        })
                        existing.add(key)

                    break

        # 4. Validate inferred relationships against the data
        for relationship in relationships:
            if relationship["source"] != "inferred":
                continue

            source_table = relationship["from_table"]
            source_column = relationship["from_column"]
            target_table = relationship["to_table"]
            target_column = relationship["to_column"]

            query = f'''
                SELECT COUNT(*)
                FROM "{source_table}" AS source
                LEFT JOIN "{target_table}" AS target
                  ON source."{source_column}" = target."{target_column}"
                WHERE source."{source_column}" IS NOT NULL
                  AND target."{target_column}" IS NULL;
            '''

            cur.execute(query)
            relationship["unmatched_values"] = cur.fetchone()[0]

        # 5. Return the combined structure
        return {
            "tables": schema,
            "relationships": relationships
        }

    finally:
        conn.close()