# Project working agreement

- Keep development local. Do not push, open a PR, deploy, or publish without new explicit user approval.
- Follow the user's stricter scope: change only `agents/event-photo-curator/`. Do not modify shared READMEs, root configuration, or other projects, including the otherwise optional agent index row.
- Ship the Python agent and local browser UI together in this project directory when publication is authorized. The UI runs through `python -m curator serve` on loopback; a hosted deployment is not required.
- The user plans to upload a video demonstrating the working local app. Do not invent a deployed URL or upload/publish the video on their behalf.
- Keep the UI dark and use beui.dev as the requested UI source. Preserve its license and attribution. The served assets are built from the React UI in frontend/, with vendored beUI buttons and inputs. Retain the prebuilt assets so ordinary users need only the Python server.
- Never include event photos, reference selfies, model weights, local state, caches, secrets, or virtual environments in a contribution.
- Follow repository README.md, CONTRIBUTING.md, agents/README.md, the template README sections, and the PR checklist. Local models and a local UI are allowed; a hosted deployment or video is not required by these documents. A video supplements runnable code. Repeat the clean-copy installation and scope/secrets checks for the final version.
- When a commit is requested, stage only this project and use `feat(agents): add event-photo-curator with documentation and setup`. When publication is explicitly authorized, push to the fork and target upstream `main`, using the repository PR template and only marking verified checks complete.
