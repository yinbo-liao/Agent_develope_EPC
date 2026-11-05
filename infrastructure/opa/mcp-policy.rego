package aiwf.mcp

default allow = false

# Admins may invoke any registered MCP tool.
allow {
  input.role == "admin"
}

# Operators may use non-destructive tools.
allow {
  input.role == "operator"
  input.tool != "delete_repository"
  input.tool != "execute_sql"
}

# Reviewers may read repository context but not mutate it.
allow {
  input.role == "reviewer"
  input.server == "github"
  startswith(input.tool, "get_")
}

allow {
  input.role == "reviewer"
  input.server == "github"
  startswith(input.tool, "list_")
}