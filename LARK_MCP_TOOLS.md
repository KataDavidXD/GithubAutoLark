# Lark MCP Tools Reference


https://open.larksuite.com/document/faq/trouble-shooting/how-to-obtain-openid

## Quick Reference Table

| Tool Name                            | Description                     | Key Parameters                                                                                              |
| :----------------------------------- | :------------------------------ | :---------------------------------------------------------------------------------------------------------- |
| `bitable_v1_app_create`            | Create a Base App               | **data**: `name`, `folder_token`, `time_zone`                                                   |
| `bitable_v1_appTable_create`       | Create table in Base            | **data**: `table<br>`**path**: `app_token`                                                  |
| `bitable_v1_appTableField_list`    | List all fields in a table      | **params**: `view_id`, `page_token`, `page_size<br>`**path**: `app_token`, `table_id` |
| `bitable_v1_appTable_list`         | List all tables in app          | **params**: `page_token`, `page_size<br>`**path**: `app_token`                            |
| `bitable_v1_appTableRecord_create` | Create a record                 | **data**: `fields<br>`**path**: `app_token`, `table_id`                                   |
| `bitable_v1_appTableRecord_search` | Search records (max 500)        | **data**: `filter`, `sort`, `field_names<br>`**path**: `app_token`, `table_id`        |
| `bitable_v1_appTableRecord_update` | Update a record                 | **data**: `fields<br>`**path**: `app_token`, `table_id`, `record_id`                    |
| `contact_v3_user_batchGetId`       | Get user ID via email/mobile    | **data**: `emails`, `mobiles`                                                                     |
| `docx_v1_document_rawContent`      | Get document plain text         | **path**: `document_id`                                                                             |
| `drive_v1_permissionMember_create` | Add document permissions        | **data**: `member_type`, `member_id`, `perm<br>`**path**: `token`                       |
| `im_v1_chat_create`                | Create a group chat             | **data**: `name`, `user_id_list`, `bot_id_list`                                                 |
| `im_v1_chat_list`                  | List groups where bot is member | **params**: `page_size`                                                                             |
| `im_v1_chatMembers_get`            | Get group member list           | **path**: `chat_id`                                                                                 |
| `im_v1_message_create`             | Send message                    | **data**: `receive_id`, `msg_type`, `content<br>`**params**: `receive_id_type`          |
| `im_v1_message_list`               | Get chat history                | **params**: `container_id_type`, `container_id`                                                   |
| `wiki_v1_node_search`              | Search Wiki                     | **data**: `query`                                                                                   |
| `wiki_v2_space_getNode`            | Get Wiki node info              | **params**: `token`                                                                                 |
| `docx_builtin_search`              | Search documents                | **data**: `search_key`                                                                              |
| `docx_builtin_import`              | Import markdown to document     | **data**: `markdown`, `file_name`                                                                 |

---

## Tested Operations & Examples

All examples below have been tested and verified on 2026-02-10.

### 1. Create Base App

Creates a new multidimensional table (Base) application.

**Input:**

```json
{
  "data": {
    "name": "New App"
  }
}
```

**Output:**

```json
{
  "app": {
    "app_token": "GYLJbQss1ajj1YsOQuDjOmsIpWg",
    "default_table_id": "tblZDBbYYhjTL7Zh",
    "name": "New App",
    "url": "https://wjpsitm2t61f.jp.larksuite.com/base/GYLJbQss1ajj1YsOQuDjOmsIpWg"
  }
}
```

---

### 2. Create Table with Fields

Creates a new table inside a Base with custom fields.

**Field Types:**

| Type Code | UI Type      | Description             |
| :-------- | :----------- | :---------------------- |
| 1         | Text         | Multi-line text         |
| 2         | Number       | Numeric value           |
| 3         | SingleSelect | Single option dropdown  |
| 4         | MultiSelect  | Multiple options        |
| 5         | DateTime     | Date picker             |
| 7         | Checkbox     | Boolean checkbox        |
| 11        | User         | Person field (Assignee) |
| 13        | Phone        | Phone number            |
| 15        | Url          | Hyperlink               |

**Input:**

```json
{
  "data": {
    "table": {
      "name": "Tasks",
      "fields": [
        {"field_name": "Task Name", "type": 1},
        {"field_name": "Assignee", "type": 11},
        {"field_name": "Status", "type": 3, "property": {
          "options": [
            {"name": "To Do"},
            {"name": "In Progress"},
            {"name": "Done"}
          ]
        }},
        {"field_name": "Due Date", "type": 5}
      ]
    }
  },
  "path": {
    "app_token": "GYLJbQss1ajj1YsOQuDjOmsIpWg"
  }
}
```

**Output:**

```json
{
  "table_id": "tblKgouyrowdWE5e",
  "default_view_id": "vewdEHDsTS",
  "field_id_list": ["fldy1Q7bGS", "fldEz3YKK7", "fldJw7txaH", "fldaQec6i5"]
}
```

---

### 3. List Fields in Table

Retrieves all fields and their properties from a table.

**Input:**

```json
{
  "path": {
    "app_token": "GYLJbQss1ajj1YsOQuDjOmsIpWg",
    "table_id": "tblKgouyrowdWE5e"
  }
}
```

**Output:**

```json
{
  "items": [
    {"field_id": "fldy1Q7bGS", "field_name": "Task Name", "type": 1, "is_primary": true},
    {"field_id": "fldEz3YKK7", "field_name": "Assignee", "type": 11, "property": {"multiple": true}},
    {"field_id": "fldJw7txaH", "field_name": "Status", "type": 3, "property": {
      "options": [
        {"id": "optCkSRgd2", "name": "To Do", "color": 0},
        {"id": "optcjTR47U", "name": "In Progress", "color": 1},
        {"id": "optAghlZWn", "name": "Done", "color": 2}
      ]
    }},
    {"field_id": "fldaQec6i5", "field_name": "Due Date", "type": 5}
  ],
  "total": 4
}
```

---

### 4. Create Record (Add Task)

Creates a new row/record in a table.

**Important:** Field names in `fields` object must match exactly (including spaces).

**Input:**

```json
{
  "data": {
    "fields": {
      "Task Name": "First Test Task",
      "Status": "To Do",
      "Due Date": 1739145600000
    }
  },
  "path": {
    "app_token": "GYLJbQss1ajj1YsOQuDjOmsIpWg",
    "table_id": "tblKgouyrowdWE5e"
  }
}
```

**Output:**

```json
{
  "record": {
    "record_id": "recvaNDQR9aVTa",
    "fields": {
      "Task Name": "First Test Task",
      "Status": "To Do",
      "Due Date": 1739145600000
    }
  }
}
```

---

### 5. Search Records

Queries existing records in a table.

**Input:**

```json
{
  "path": {
    "app_token": "GYLJbQss1ajj1YsOQuDjOmsIpWg",
    "table_id": "tblKgouyrowdWE5e"
  }
}
```

**Output:**

```json
{
  "items": [
    {
      "record_id": "recvaNDQR9aVTa",
      "fields": {
        "Task Name": [{"text": "First Test Task", "type": "text"}],
        "Status": "To Do",
        "Due Date": 1739145600000
      }
    }
  ],
  "total": 1
}
```

---

### 6. Update Record

Updates an existing record's fields.

**Input:**

```json
{
  "data": {
    "fields": {
      "Status": "In Progress"
    }
  },
  "path": {
    "app_token": "GYLJbQss1ajj1YsOQuDjOmsIpWg",
    "table_id": "tblKgouyrowdWE5e",
    "record_id": "recvaNDQR9aVTa"
  }
}
```

**Output:**

```json
{
  "record": {
    "record_id": "recvaNDQR9aVTa",
    "fields": {
      "Status": "In Progress"
    }
  }
}
```

---

### 7. Assign Member to Task

To assign a user to a task, you need their `open_id`.

**Step 1: Get User ID via Email**

```json
{
  "data": {
    "emails": ["user@example.com"]
  },
  "params": {
    "user_id_type": "open_id"
  }
}
```

**Step 2: Update Record with Assignee**

```json
{
  "data": {
    "fields": {
      "Assignee": [{"id": "ou_xxxxxxxxxxxxxxxx"}]
    }
  },
  "path": {
    "app_token": "...",
    "table_id": "...",
    "record_id": "..."
  }
}
```

---

## Test Summary

| Operation       | Tool                                        | Status                        | Notes                               |
| :-------------- | :------------------------------------------ | :---------------------------- | :---------------------------------- |
| Create Base App | `bitable_v1_app_create`                   | **Success**             | Returns app_token and URL           |
| Create Table    | `bitable_v1_appTable_create`              | **Success**             | Supports custom fields with options |
| List Fields     | `bitable_v1_appTableField_list`           | **Success**             | Returns field IDs and properties    |
| Create Record   | `bitable_v1_appTableRecord_create`        | **Success**             | Field names must match exactly      |
| Search Records  | `bitable_v1_appTableRecord_search`        | **Success**             | Supports filtering and sorting      |
| Update Record   | `bitable_v1_appTableRecord_update`        | **Success**             | Can update individual fields        |
| Assign Member   | `contact_v3_user_batchGetId` + `update` | **Requires User Email** | Need email to get open_id first     |

---

## Common Errors

| Error Code | Message           | Cause                    | Solution                               |
| :--------- | :---------------- | :----------------------- | :------------------------------------- |
| 1254045    | FieldNameNotFound | Field name doesn't match | Use exact field names including spaces |
| 1254007    | RecordNotFound    | Invalid record_id        | Verify record exists via search        |
| 1254001    | TableNotFound     | Invalid table_id         | Use `appTable_list` to get valid IDs |
