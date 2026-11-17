| Method | Legacy condition | View registration |
| --- | --- | --- |
| GET | `/api/health` | registered (inspect delegation) |
| GET | `/api/processes` | registered (inspect delegation) |
| GET | `/api/scheduler-tasks` | registered (inspect delegation) |
| GET | `/api/scheduler-tasks/code-review` | registered (inspect delegation) |
| GET | `/api/settings/storage` | registered (inspect delegation) |
| GET | `/api/settings/storage/open` | registered (inspect delegation) |
| POST | `/api/central-client/start` | registered (inspect delegation) |
| POST | `/api/central-client/stop` | registered (inspect delegation) |
| POST | `/api/central-server/cleanup` | registered (inspect delegation) |
| POST | `/api/central-server/start` | registered (inspect delegation) |
| POST | `/api/central-server/stop` | registered (inspect delegation) |
| POST | `/api/code-review/setup` | registered (inspect delegation) |
| POST | `/api/openai-agent/chat` | registered (inspect delegation) |
| POST | `/api/openai-agent/cleanup` | registered (inspect delegation) |
| POST | `/api/openai-agent/start` | registered (inspect delegation) |
| POST | `/api/openai-agent/stop` | registered (inspect delegation) |
| POST | `/api/scheduler-tasks/code-review` | legacy only |
| POST | `/api/scheduler-tasks/code-review/choose` | registered (inspect delegation) |
| POST | `/api/scheduler-tasks/code-review/config` | registered (inspect delegation) |
| POST | `/api/scheduler-tasks/code-review/open` | registered (inspect delegation) |
| POST | `/api/scheduler-tasks/code-review/run` | registered (inspect delegation) |
| POST | `/api/scheduler-tasks/code-review/stop` | registered (inspect delegation) |
| POST | `/api/scheduler-tasks/create` | registered (inspect delegation) |
| POST | `/api/scheduler-tasks/delete` | registered (inspect delegation) |
| POST | `/api/scheduler/start` | registered (inspect delegation) |
| POST | `/api/scheduler/stop` | registered (inspect delegation) |
| POST | `/api/settings/storage` | registered (inspect delegation) |
| POST | `/api/settings/storage/choose` | registered (inspect delegation) |
| POST | `/api/settings/storage/reset` | registered (inspect delegation) |
Scope: literal path equality only; registration does not prove implementation or exclude delegation.
