#ToTi
http://3.38.58.74/

1. 실행방법
- docker compose up -d --build 실행
- docker exec -it toti-app sh -c "python bgm-import.py" 실행하여 bgm파일을 db저장
- 이 후 docker exec -it toti-db psql -U toti_user -d toti_db -c "SELECT id, title, file_url FROM track;" 실행하여 db저장 확인
  
2. .env 필요 내용
- 필수내용
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD

GEMINI_API_KEY

DATABASE_URL

SECRET_KEY

ACCESS_TOKEN_EXPIRE_HOURS=2


git clone https://github.com/azure5finger-cmyk/marmot.git toti

CD testing#1

CD testing#2

CD testing#3
