# Order Info Extractor

Extracts order information from Outlook emails using AI and outputs Turner's ERP-compatible text files.

Emails are fetched via Microsoft Graph API, parsed with OpenAI to identify products/quantities/accounts, and matched against Turner Dairy's product catalog.

## Output

**ERP text file** (tab-delimited, ready for Turner's ERP):
```
H	8306	8306	02/18/26
D	3	cases	24
D	31	cases	36
E
```

## Setup

### 1. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp config.example.json config.json
```

Edit `config.json` with:

- **Microsoft Graph API** credentials (client ID, client secret, tenant ID, user email) — requires `Mail.Read` and `Mail.ReadWrite` application permissions
- **OpenAI API** key

### 3. Run

**Web UI** (recommended):
```bash
python3 -m streamlit run ui_streamlit.py
```

The UI has two tabs:
- **Compose & Send** — build and send test order emails to the mailbox
- **Fetch & Process** — fetch emails from Outlook, extract orders, download ERP text file

**CLI**:
```bash
python3 main.py --limit 10
python3 main.py --subject-filter "order"
python3 main.py --from-date 2026-02-01
python3 main.py --email-id <MESSAGE_ID>
```

## Project Structure

```
main.py              CLI entry point
ui_streamlit.py      Streamlit web UI
src/
  outlook.py         Microsoft Graph API client
  ai_parser.py       OpenAI order extraction + product catalog
  order_processor.py Orchestrates text and attachment parsing
  excel_parser.py    Parses Excel attachment order forms
  erp_writer.py      Turner's ERP text file output (H/D/E format)
  product_catalog.json  Turner Dairy product catalog
  utils.py           Date parsing, HTML cleaning
```
# Order-Info-Extractor
