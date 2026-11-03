# Open Cowork

A self-hosted, Open WebUI–style workspace for **local models (Ollama)** and **any OpenAI-compatible API**, with a dedicated
**Cowork** tab: an agent that plans a task, then reads and edits files, runs commands and works directly inside your
GitHub repositories while you watch every step.

![Chat](docs/images/chat.png)

| Cowork: approve each step | Git panel: diff, commit, push, PR |
| --- | --- |
| ![Cowork approval](docs/images/cowork-approval.png) | ![Git panel](docs/images/cowork-git.png) |

## Features

**Chat**
- Ollama (native API) and OpenAI-compatible endpoints (OpenAI, LM Studio, vLLM, llama.cpp, LiteLLM, OpenRouter, Groq…), any number of connections at once
- Streaming Markdown with syntax highlighting, tables and reasoning/`<think>` display
- Edit, regenerate, stop; image attachments for vision models; automatic chat titles
- Per-chat controls: system prompt, temperature, max tokens, Ollama context length
- Chats are saved on the server, so a reply keeps generating even if you close the tab

**Cowork tab**
- Give it a task. The agent writes a plan, then uses tools: `list_files`, `read_file`, `write_file`, `edit_file`, `search_files`, `run_command`, `update_plan`
- **Ask first** mode pauses before every file edit and command (allow once, allow all, or deny). **Auto** mode runs without stopping.
- Live view of each step: streamed command output, diffs for edits, plan progress
- Send a message while it runs to steer it; stop at any time; reload the page mid-run and it picks up where it was
- Side panel with plan, changed files, a file browser (preview, upload, download) and a Git tab
- Each task works in its own folder: a fresh scratch folder in `workspaces/`, or a cloned repository in `repo/`

**GitHub integration**
- Connect with a personal access token, search your repositories and clone them into an easy-to-find **`repo/`** folder (`/repo/<owner>/<name>` in Docker)
- Before a repo task starts, the latest base branch is **pulled** and a fresh **`cowork/<task>-<id>` branch** is created, so the agent never works on `main`
- Git panel: per-file diffs, commit, pull, push and **open a pull request** without leaving the task

**Users & admin**
- **The first account becomes the admin.** Later sign-ups get the default role (`pending` by default, so an admin has to activate them)
- Sign-ups can be turned off; admins can still add accounts
- Admin panel: users and roles, model connections (with presets and connection tests), sign-up policy, Cowork limits (shell access, timeouts, steps, context length), feature toggles

## Quick start

### Docker (recommended)

With [Ollama](https://ollama.com) running on your machine:

```bash
git clone https://github.com/cametendo/open-cowork.git
cd open-cowork
docker compose up -d
```

Open http://localhost:3000 and create the first account, which becomes the admin. Cloned repositories appear in
`./repo` and Cowork scratch folders in `./workspaces`, next to the compose file.

To run Ollama in a container as well:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
```

```bash
docker compose exec ollama ollama pull qwen3:8b
```

To use an OpenAI-compatible API, copy `.env.example` to `.env` and set `OPENAI_API_BASE_URL` and `OPENAI_API_KEY`
before the first start, or add a connection later in **Admin › Connections**.

### Local (no Docker)

Requirements: Python 3.11+, Node.js 20+ (only to build the UI) and git.

```bash
./start.sh
```

This creates a virtualenv in `backend/.venv`, installs dependencies, builds the UI and serves everything on
http://localhost:8080. Repositories go to `./repo` and task folders to `./workspaces`.

To work on the code, start the API with auto-reload plus the Vite dev server on http://localhost:5173:

```bash
./start.sh --dev
```

<details>
<summary>Manual steps (Windows or custom setups)</summary>

```bash
cd frontend
npm ci
npm run build
cd ../backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m open_cowork --port 8080
```

On Windows, use `.venv\Scripts\pip` and `.venv\Scripts\python`.
</details>

## Choosing models for Cowork

Cowork relies on **tool calling**. Good local choices include `qwen3`, `qwen2.5-coder`, `llama3.1`/`llama3.3`,
`mistral-nemo`, `gpt-oss` and `devstral`. Models without tool support return an error explaining this.

Agents need context room for file contents and command output. For Ollama, Cowork runs request `num_ctx = 16384` by
default (change it in **Admin › Cowork & GitHub**; `0` uses the model's default).

## GitHub setup

1. Open **Settings › GitHub** (or **Cowork › Repositories**).
2. Create a token: a [classic token with the `repo` scope](https://github.com/settings/tokens/new?scopes=repo&description=Open%20Cowork),
   or a fine-grained token with **Contents** and **Pull requests** set to read & write.
3. Paste it and click **Connect**. The token is stored encrypted and is only used for your own requests.
4. Clone a repository from the list, or type `owner/repo`. Public repositories can be cloned without a token.
5. Start a task from the repository. When it's done, review the diff in the **Git** tab, commit, push and open a pull request.

Admins also see any git repository placed by hand in the repo folder (one or two levels deep, e.g.
`repo/my-project` or `repo/acme/my-project`).

## Configuration

Environment variables (see `.env.example`). Values marked *first boot* only seed the database; after that they are
managed in the admin panel.

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` / `HOST` | `8080` / `0.0.0.0` | Where the server listens |
| `DATA_DIR` | `backend/data` (`/app/backend/data` in Docker) | SQLite database and generated secret key |
| `REPO_DIR` | `./repo` (`/repo` in Docker) | Where repositories are cloned |
| `WORKSPACE_DIR` | `./workspaces` (`/workspaces` in Docker) | Scratch folders for Cowork tasks |
| `WEBUI_SECRET_KEY` | generated | Signs sessions and encrypts stored tokens and API keys. Keep it stable. |
| `WEBUI_NAME` | `Open Cowork` | Instance name (*first boot*) |
| `ENABLE_SIGNUP` | `true` | Allow new sign-ups (*first boot*) |
| `DEFAULT_USER_ROLE` | `pending` | `pending` or `user` (*first boot*) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Initial Ollama connection (*first boot*) |
| `ENABLE_OLLAMA_API` | `true` | Enable that connection (*first boot*) |
| `OPENAI_API_BASE_URL` / `OPENAI_API_KEY` | — | Initial OpenAI-compatible connection (*first boot*) |
| `COWORK_ALLOW_SHELL` | `true` | Let the agent run shell commands (*first boot*) |
| `JWT_EXPIRES_HOURS` | `168` | Session lifetime |
| `GITHUB_API_URL` / `GITHUB_URL` | github.com | For GitHub Enterprise Server |
| `CORS_ALLOW_ORIGINS` | — | `;`-separated origins, only needed if the UI is served elsewhere |
| `DATABASE_URL` | SQLite in `DATA_DIR` | SQLAlchemy URL |

## Security notes

Cowork is a real agent: with shell access on, it can run any command the server process can. Treat it like giving
someone a terminal.

- In Docker it is confined to the container and the folders you mount (`repo/`, `workspaces/`). Running locally, it
  has your user's permissions.
- Admins can turn off shell commands, which limits the agent to reading and editing files inside the task's workspace.
- File tools are confined to the task's workspace (symlinks included). Commands run with a scrubbed environment, so
  the server's secrets and API keys aren't visible to them.
- **Ask first** mode (the default) requires approval for every edit and command.
- The GitHub token is never written to `.git/config` or given to the agent. Pushing and opening pull requests happen
  from the Git panel. Repository hooks are disabled for git commands the server runs, and the token is only sent to
  the clone's own GitHub remote.
- Only trusted users should get Cowork access in multi-user setups. You can disable Cowork for non-admins.

## Development

```
backend/              FastAPI app (python -m open_cowork)
  open_cowork/
    routers/          auth, users, admin, connections, chats, cowork, github
    providers/        Ollama + OpenAI-compatible streaming clients
    cowork/           agent loop, tools, prompts, workspaces
    github/           GitHub API client and git helpers
  tests/              pytest suite + mock_llm.py (fake Ollama/OpenAI server)
frontend/             React + Vite + Tailwind UI
```

Run the tests:

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

To build the UI without a GPU, run the bundled fake model server and add it as a connection (Ollama type
`http://localhost:11555`, or OpenAI type `http://localhost:11555/v1`):

```bash
backend/.venv/bin/python backend/tests/mock_llm.py --port 11555
```

## License

MIT
