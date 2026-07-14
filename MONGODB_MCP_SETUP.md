# MongoDB MCP Server Setup

This guide sets up MongoDB Atlas integration with Claude Code for full context access to your geotrade databases.

## Installation

### 1. Install Dependencies

```bash
cd C:\Users\karti\.claude\mcp-servers
npm install
```

### 2. Set MongoDB Connection String

Add your MongoDB Atlas connection string as an environment variable:

**Option A: Windows Environment Variable (Persistent)**
```powershell
[Environment]::SetEnvironmentVariable("MONGODB_URI", "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority", "User")
```

**Option B: .env file (Project-local)**
Create `.env` in the geotrade_v2 root:
```
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
```

**Option C: Claude Code Settings**
Edit `.claude/settings.json`:
```json
{
  "env": {
    "MONGODB_URI": "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority"
  }
}
```

### 3. Find Your Connection String

In MongoDB Atlas:
1. Go to Clusters → Connect
2. Choose "Drivers" connection method
3. Copy the connection string (looks like: `mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority`)
4. Replace `<username>` and `<password>` with your credentials

## Available Tools

Once configured, Claude has access to these MongoDB tools:

### Query Operations
- **`list_databases`** - Show all databases
- **`list_collections`** - List collections in a database
- **`find_documents`** - Query documents with filters
- **`get_schema`** - Inspect collection structure

### Write Operations
- **`insert_document`** - Add new documents
- **`update_document`** - Modify documents
- **`delete_documents`** - Remove documents

### Advanced
- **`aggregate`** - Run aggregation pipelines for complex queries

## Usage Examples

### Let Claude Explore Your Data

Ask Claude:
```
"Show me all databases and collections in my MongoDB"
"What's the schema of the 'trades' collection?"
"Find trades from the last 7 days"
"Aggregate trading volume by country"
```

### Provide Context to Claude

Claude can now:
- Understand your geotrade data structure
- Query trading data for analysis
- Insert/update geotrade records
- Run aggregations for insights
- Provide full database context for tasks

## Security Notes

⚠️ **Important:**
- Never commit your `.env` or `.mcp.json` with credentials
- Use environment variables, not hardcoded connection strings
- MongoDB Atlas connection strings include credentials—treat as secrets
- Use IP whitelisting in MongoDB Atlas for additional security
- Consider using MongoDB Atlas database user credentials with minimal required permissions

## Troubleshooting

### MCP Server Won't Start
```bash
# Check if Node.js is available
node --version

# Test the server directly
node C:\Users\karti\.claude\mcp-servers\mongodb-server.js
```

### Connection String Issues
- Verify the connection string format
- Check MongoDB Atlas user credentials
- Ensure IP address is whitelisted in Atlas
- Look for special characters that need URL encoding

### No Tools Available
Run `/mcp` in Claude Code to see connected servers:
```
/mcp
```

Should show `mongodb` server with available tools.

### Environment Variable Not Found
- On Windows, restart Claude Code after setting environment variables
- Or use `.env` file and ensure it's loaded
- Check that `MONGODB_URI` is properly set

## Testing

Once set up, test with Claude:

1. **List all databases:**
   ```
   Use the MongoDB tool to list all databases
   ```

2. **Explore a collection:**
   ```
   Get the schema of the 'countries' collection
   ```

3. **Query data:**
   ```
   Find documents from the 'trades' collection where country='US'
   ```

## Next Steps

- Use `/mcp` to verify the server is running
- Ask Claude to explore your data structure
- Build commands/agents that leverage full database context
- Use Claude's analysis capabilities on your trading data

## Reference

- [MongoDB URI Connection String](https://docs.mongodb.com/manual/reference/connection-string/)
- [MongoDB Atlas Security](https://docs.mongodb.com/manual/security/)
- [MCP Protocol](https://modelcontextprotocol.io/)
