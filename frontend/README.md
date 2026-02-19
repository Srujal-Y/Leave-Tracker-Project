# Leave Tracker Frontend (Next.js + shadcn/ui)

This frontend uses real `shadcn/ui` components and connects to your Django backend through `/api/`.

## Run Locally

1. Copy env template:

```bash
cp .env.example .env.local
```

2. Install dependencies:

```bash
npm install
```

3. Start frontend:

```bash
npm run dev
```

Open `http://localhost:3000`.

## Required Backend

Run Django server in project root:

```bash
python manage.py runserver
```

Default API base URL expected by frontend:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api
```

## Implemented Routes

- `/login`
- `/dashboard`
- `/leave/apply`
- `/approvals`

