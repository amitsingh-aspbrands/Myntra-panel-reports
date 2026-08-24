# Myntra Seller Panel (MDirect) MCP Server

An MCP server that automates Myntra MDirect seller panel operations using Playwright:
- Login with email/password
- Schedule JIT Inventory Download reports
- Download completed reports as CSV

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate

pip install -e .
playwright install chromium
```

### 2. Configure credentials

```bash
copy .env.example .env
```

Edit `.env` with your Myntra seller panel email and password.

### 3. Register with Kiro

Create `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "myntra-scraper": {
      "command": "python",
      "args": ["-m", "myntra_scraper_mcp.server"],
      "cwd": "d:\\MCP Myntra",
      "env": {
        "PYTHONPATH": "d:\\MCP Myntra\\src"
      },
      "disabled": false
    }
  }
}
```

## Available Tools

| Tool | What it does |
|------|--------------|
| `login` | Authenticates to `accounts.myntra.com` with email/password, saves session |
| `schedule_report` | Goes to MDirect Selfserve, selects "JIT INVENTORY DOWNLOAD", clicks SUBMIT |
| `download_report` | Goes to MDirect Airflow, searches, finds completed report, downloads SUCCESS FILE |

## Usage Flow

1. **login** — Authenticate (only needed once, session is reused)
2. **schedule_report** — Triggers report generation
3. **download_report** — Wait a few minutes, then download the generated CSV

## URLs Used

- Login: `accounts.myntra.com/emaillogin`
- Schedule: `mdirect.myntrainfo.com/Selfserve`
- Download: `mdirect.myntrainfo.com/Airflow`

## First Run

The browser launches visibly (`headless=False`) so you can verify selectors work. Once confirmed, change to `headless=True` in `server.py` for background operation.

## Troubleshooting

- **Session expired**: Delete `auth_state.json` and run `login` again
- **Selectors don't match**: Run with `headless=False`, inspect the page, update selectors in `server.py`
- **Report not ready**: Wait a few minutes after scheduling before trying `download_report`
- **Playwright not found**: Run `playwright install chromium`
