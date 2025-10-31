專案結構（後端重點）

backend/
├─ app/
│  ├─ main.py
│  ├─ database.py          # create_engine / SessionLocal / Base
│  ├─ models.py            # models 都使用 from app.database import Base
│  ├─ routers/             # FastAPI routers（包含 api.py）
│  └─ ...                 
├─ alembic/
│  └─ versions/            # 版本化遷移檔（請務必納入版控）
├─ alembic.ini
├─ requirements.txt
├─ docker-compose.yml      # 啟 DB + Adminer + migrate + api（全套一鍵啟動）
├─ .env.development        # 本機 DB 連線（不要上傳密碼到公開庫）
└─ README

簡介
--
這份 README 給後端開發者快速上手的指引：
- 使用 docker-compose 一鍵啟動 db → migrate → api → adminer。
- 用 Alembic 管理資料庫遷移（本機與 CI/production 皆一致）。
- Dockerfile 採用 uv 基底鏡像以加速建置。

1) 快速開始（docker-compose 一鍵啟動）

docker-compose.yml 預設：Postgres 對外 5433→5432（可選）、Adminer 8080→8080、API 8081→8081。

啟動（在 `backend/` 下）：

```cmd
docker compose up --build
```

檢查狀態：

```cmd
docker compose ps
docker logs townpass_db --tail 50
```

服務網址：

- API（FastAPI Swagger）：http://127.0.0.1:8081/docs
- Adminer（DB 管理）：http://localhost:8080

關閉：

```cmd
docker compose down
```

若需要重置資料（會刪掉 DB 資料）：

```cmd
docker compose down -v
```

連線資訊（選用，僅當你要從主機直連 DB 時）

- DB URL：postgresql+psycopg://admin:password@localhost:5433/townpass_db
  - 若 5433 於 Windows 上被限制/占用，可改用其他埠或直接移除 `db.ports`，改由 Adminer 訪問 DB。
- Adminer（System: PostgreSQL）：http://localhost:8080（帳號 admin / 密碼 password）

2) 設定環境變數

開發時請在 `backend/.env.development` 或 `backend/.env` 中放入：

```text
DATABASE_URL=postgresql+psycopg://admin:password@localhost:5433/townpass_db
```

app/config.py 會讀取 `.env.development`（請確認設定檔中的 `env_file` 對應正確）。

3) 在本機啟動後端（不經容器，開發模式，選用）

```cmd
cd backend
.venv\Scripts\activate    # 如果你有 virtualenv
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打開 Swagger UI： http://127.0.0.1:8000/docs

4) 重新建構 / 在容器內執行 api

如果你是使用 Docker image（`docker compose up api` 或 `docker compose up --build`），在修改後端程式碼後必須重建 image 才會生效。常見做法：

```cmd
cd backend
docker compose up -d --build api
docker compose logs api --tail 200
```

開發時若要即時反映變更，可在 `docker-compose.yml` 的 `api` 服務加入掛載（volume）：

```yaml
services:
  api:
    volumes:
      - ./app:/app/app:rw
```

（注意：容器內必須有相容的 Python 套件與開發工具）

5) Alembic（資料庫遷移）

請用 Alembic 管理資料庫變更，切勿在 production 直接靠 `create_all` 建表。

快速範例（在本機或 container 內執行）：

```cmd
cd backend
# 產生 migration（autogenerate）
alembic revision --autogenerate -m "add xxx"
# 套用 migration
alembic upgrade head
```

若在 container 內執行（建議在 compose network 裡執行，能解析 service name `db`）：

```cmd
docker compose up -d api db
docker compose exec api alembic revision --autogenerate -m "add tables"
docker compose exec api alembic upgrade head

compose 亦已定義 `migrate` 服務，`docker compose up` 會在 DB 健康後自動執行：

```cmd
docker compose up --build
# 流程：db(健康) → migrate(成功結束) → api 啟動
```
```

常見問題：
- `Can't proceed with --autogenerate ... does not provide a MetaData object`：請確認 `alembic/env.py` 中 `target_metadata` 指向 `app.database.Base.metadata`。
- `relation ... does not exist`：表示 table 尚未建立，請執行 Alembic migration 或在本機暫時使用 `Base.metadata.create_all(bind=engine)`（僅限開發）。

6) 後端 API 與前端整合

- 我們已新增 `TestRecord` model（`app/models.py`）與對應的 Pydantic schema，並在 `app/routers/api.py` 提供：
  - GET `/api/test_records` — 列表
  - POST `/api/test_records` — 新增
- 前端開發伺服器預設跑在 `http://localhost:5173`。請設定：
  - `VITE_API_BASE=http://127.0.0.1:8081`（compose 啟動的 api）
  - 或 `VITE_API_BASE=http://127.0.0.1:8000`（本機 uvicorn 啟動）
- 在程式端請使用絕對網址或 URL builder，避免出現 `http://localhost:5173/127.0.0.1:8081/...` 的錯誤拼接。

7) 常見除錯提示

- 404 for new route: 表示運行中的 `api` container 沒有載入最新程式（請重建或使用 volume 掛載）。
- 密碼驗證失敗（`password authentication failed`）：很可能是 Postgres volume 已有舊密碼，解法：
  - 若可以丟棄資料：`docker compose down -v` 然後重啟 db；
  - 若要保留資料：用 postgres superuser 修改使用者密碼（`docker exec -it townpass_db psql -U postgres -c "ALTER USER admin WITH PASSWORD 'password';"`），或新增一個 DB 使用者並更新 `DATABASE_URL`。
- 若 Alembic autogenerate 沒偵測變更：確認 `alembic/env.py` 的 `target_metadata` 已指向 `app.database.Base.metadata`，並且 models 已匯入（alembic 需要匯入 model module 才能看到 metadata）。

7) 其他建議

- 把敏感資訊（service account、明碼密碼）放到 CI / Secret Manager，不要直接放到版控。
- 開發流程：本機用 `uvicorn --reload` 或用 compose 的 `api`；在 CI 用 `alembic upgrade head` 再部署到 Cloud Run / GKE / 其他。

附註：Dockerfile 改為 uv 基底鏡像，建置採用：

```Dockerfile
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
```

如果你要我幫忙把 README 再收斂成 README.dev（給新開發者）或 README.prod（部署指南），我可以繼續分拆與補充具體範例。