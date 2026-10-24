# Accessibility Agent

This project implements an end-to-end Accessibility CI/CD Audit & Remediation Agent along with a local Model Context Protocol (MCP) server.

## Features

- **Accessibility Auditing**: Headless Playwright integration with `@axe-core/playwright` for comprehensive WCAG 2.1 & 2.2 AA scanning.
- **Report Generation**: Parses AxeResults into structured JSON summaries, GitHub PR Markdown tables, and PDF reports for easy review.
- **AI Remediation**: Utilizes the Gemini API (`gemini-2.5-pro`) to suggest and apply accessibility fixes.
- **Code Mapping**: Scans the workspace to map DOM selectors and HTML snippets to their corresponding source files.
- **MCP Server**: Provides a local Model Context Protocol server for seamless integration with Cursor and other tools.
- **CI/CD Integration**: GitHub Actions workflow to automate PR checks, generate reports, and trigger AI fixes via comments.

## Getting Started

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/gdgcblr/open-source-agents.git
    cd open-source-agents/agents/accessibility-agent
    ```
2.  **Install dependencies**:
    ```bash
    npm install
    ```
3.  **Configure environment variables**:
    Copy `.env.example` to `.env` and fill in your Gemini API key.
    ```bash
    cp .env.example .env
    ```
4.  **Build the project**:
    ```bash
    npm run build
    ```
5.  **Run the MCP Server (for local development/testing)**:
    ```bash
    npm run mcp-server
    ```
6.  **Use the CLI**:
    ```bash
    npm start -- audit <url>
    npm start -- audit <url> --format pdf --output report.pdf
    npm start -- fix <file-path> <line-number>
    ```

### Testing with Demo Website

A sample website with various accessibility issues is provided in the `demo/` folder to facilitate testing and verification of the accessibility agent.

**1. Serve the Demo Website:**
To serve the `index.html` file from the `demo/` folder, open a new terminal, navigate to the `demo/` directory, and use `npx http-server`:
```bash
    cd demo
npx http-server
```
This will typically serve the demo site at `http://localhost:8080`. Keep this terminal open while testing.

**2. Run Audits against the Demo Website:**
In the `accessibility-agent` directory, you can now run audits against the locally served demo website:
```bash
# Audit and output Markdown
npm start -- audit http://localhost:8080 --format markdown

# Audit and output PDF
npm start -- audit http://localhost:8080 --format pdf --output demo-report.pdf
```

### Project Structure

```
agents/accessibility-agent/
├── package.json
├── tsconfig.json
├── .env.example
├── README.md
├── .cursor/
│   └── mcp.json
├── src/
│   ├── core/
│   │   ├── audit.ts
│   │   └── reporter.ts
│   ├── agent/
│   │   ├── ai-fixer.ts
│   │   └── mapper.ts
│   ├── mcp/
│   │   └── server.ts
│   ├── ci/
│   │   └── github-action.ts
│   └── index.ts
├── demo/
└── .github/workflows/
    └── a11y-pipeline.yml
```
