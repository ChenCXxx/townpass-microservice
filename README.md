# TownPass — Microservice + Frontend
## 專案結構
```text
.
├─ backend/                         # FastAPI + SQLAlchemy + Alembic
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ database.py                # create_engine / SessionLocal / Base
│  │  ├─ models.py                  # models 請 from app.database import Base
│  │  └─ routers/                   # 路由（含 api.py）
│  ├─ alembic/
│  │  └─ versions/                  # 遷移檔（必納入版控）
│  ├─ alembic.ini
│  ├─ requirements.txt
│  ├─ docker-compose.yml            # 本機只啟 DB + Adminer
│  └─ README.md
│
├─ frontend/                        # Vite + Vue
│  ├─ src/
│  │  ├─ components/
│  │  ├─ router/                    # Vue Router 設定
│  │  └─ service/                   # 封裝 API 呼叫（fetch/axios）
│  ├─ index.html
│  ├─ package.json
│  └─ README.md
│
├─ TownPass/                        # Flutter App（可選）
│  └─ ...
│
├─ .gitignore
└─ README.md
```

## Description

這個專案包含三個主要部分：

- `backend/`：FastAPI + SQLAlchemy 後端，使用 Alembic 管理資料庫遷移。
- `frontend/`：Vite + Vue 前端（使用 pnpm），封裝 API 呼叫在 `frontend/src/service/`。
- `TownPass/`：Flutter 行動 App（Mobile client，非必要做 local dev）。

目的：建立可部署到 Cloud Run 與 Firebase 的微服務範例，並示範本地開發流程（含 Docker Postgres 與 Adminer）。

---

## Requirement

- 作業系統：macOS / Linux / Windows
- Python：3.11+
- Node.js：18+（或符合 `frontend/package.json` 的版本）
- 套件管理：pnpm（也可使用 npm / yarn）
- Docker & Docker Compose（建議用於執行 Postgres + Adminer）

建議工具：git、curl / httpie、VS Code（搭配 Python、Volar、ESLint、Flutter 擴充）。

---

## .env Setting

Backend（`backend/.env` 或 `backend/.env.development`）：

```text
# 範例（本機開發，Docker Compose 對應 host 5433 -> container 5432）
DATABASE_URL=postgresql+psycopg://admin:password@localhost:5433/townpass_db
```

Frontend（`frontend/.env`）：

```text
VITE_API_BASE=http://127.0.0.1:8000
```

CI / Deploy secrets（放在 GitHub Secrets / Cloud Secret Manager）：
- `GCP_SA_KEY`, `FIREBASE_SA`, `PROJECT_ID`, `DB_USER`, `DB_PASS`, `DB_NAME`, `INSTANCE_CONNECTION_NAME`, etc.


---

## Alembic

修改 app/models.py 之後 → 產生遷移檔 → 套用 → 驗證

```bash
# 1) 修改了 app/models.py 後 → 產生遷移檔（自動比對）
alembic revision --autogenerate -m "add foo column on users"

# 2) 套用遷移到 Docker DB
alembic upgrade head

# 3) 檢查結果（用 Adminer 或 psql）
psql "postgresql://admin:password@localhost:5433/townpass_db" -c '\dt'
```

常用指令：
```bash
# 目前 DB 版本
alembic current

# 歷史紀錄
alembic history

# 回退一版（謹慎使用）
alembic downgrade -1
```

常見狀況排解

- `No changes in schema detected` → 確認 Alembic 有 import 你的 models。

- 需要清庫重來（本機）：
    ```cmd
    docker compose down -v
    docker compose up -d db
    alembic upgrade head
    ```

- 務必提交遷移檔：`alembic/versions/*.py` 需進版控，避免團隊環境不一致。


---

## Build Setup (Local)

後端（local dev）：

```cmd
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger UI： http://127.0.0.1:8000/docs

只用 Docker 跑資料庫（建議）：

```cmd
cd backend

docker compose up -d db adminer

# Adminer: http://localhost:8080
```

快速檢查 DB 與 logs：

```cmd
docker compose ps

docker logs townpass_db --tail 50
```

前端（local dev）：

```cmd
cd frontend

pnpm install
pnpm dev

# default: http://localhost:5173
```

前端會使用 `VITE_API_BASE` 連到後端 API（開發時預設為 http://127.0.0.1:8000）。

---

## Flutter（TownPass）

在 App 中加入「微服務」入口，destinationUrl 指向前端（Firebase Hosting）：

```dart
enum MyServiceItemId {
  // ...其他項目
  microService,
}

extension MyServiceIdExt on MyServiceItemId {
  MyServiceItem get item {
    switch (this) {
      case MyServiceItemId.microService:
        return MyServiceItem(
          title: '微服務',
          description: '更多市政服務，持續開發中',
          icon: Assets.svg.icon1999phoneS.svg(),
          category: MyServiceCategory.cityService,
          // 重點：前端網址（Firebase Hosting）
          destinationUrl: 'https://townpass-microservice.web.app/',
        );
      // ...其他 case
    }
  }
}
```

---

## Architecture

- `backend/`: FastAPI + SQLAlchemy + Alembic
- `frontend/`: Vite + Vue（pnpm）
- `TownPass/`: Flutter app

---

## Troubleshooting

- 404 for new route: 運行中的 `api` container 未載入最新程式，請重建 `api` image：

```cmd
cd backend
docker compose up -d --build api
docker compose logs api --tail 200
```

- password authentication failed: 可能是 Postgres volume 裡已有舊密碼；若可清掉資料：

```cmd
docker compose down -v
docker compose up -d db adminer
```

或在容器內更新密碼（保留資料）：

```cmd
docker exec -it townpass_db psql -U postgres -c "ALTER USER admin WITH PASSWORD 'password';"
```

- alembic autogenerate 不偵測變更：檢查 `alembic/env.py` 中的 `target_metadata` 與 models 匯入。

---

## Quick start checklist

1. `docker compose up -d`（啟 DB 與 Adminer）

2. `backend/.env` 設好 `DATABASE_URL` 指向 localhost:5433

3. `alembic upgrade head`（初始化資料表）

4. `uvicorn app.main:app --reload`（後端啟動）

5. `cd frontend` → `pnpm dev`（前端啟動）
