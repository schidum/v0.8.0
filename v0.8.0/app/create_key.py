import secrets 
key = secrets.token_urlsafe(64)
with open('.env', 'w', encoding='utf-8') as f:
    f.write(f'SECRET_KEY={key}\n')
print('✅ SECRET_KEY успешно записан в файл .env')
print(f'SECRET_KEY={key}')
