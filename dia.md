erDiagram
    FILE_NODES ||--o{ DEPENDENCIES : "imports / imported_by"
    FILE_NODES ||--o{ SYMBOL_DEFINITIONS : "defines"
    FILE_NODES ||--o{ SYMBOL_REFERENCES : "calls"

    FILE_NODES {
        string file_path PK
        string sha256
        int total_lines
        timestamp last_indexed
    }

    DEPENDENCIES {
        int id PK
        string source_file FK
        string target_file FK
        string raw_import
    }

    SYMBOL_DEFINITIONS {
        int id PK
        string file_path FK
        string symbol_name
        string symbol_type
        int start_line
        int end_line
    }

    SYMBOL_REFERENCES {
        int id PK
        string caller_file FK
        string symbol_name
        int line_number
    }
