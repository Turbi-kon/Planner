# Как выложить «Лист» на GitHub

Git у тебя уже установлен. Публикуй содержимое папки `daily_planner`: `main.py`, папки `planner`, `tests`, `docs`, оба README и остальные исходники. В репозитории они должны лежать в корне. Русский README будет главной страницей, английский доступен по ссылке в начале.

## 1. Создай пустой репозиторий

На [github.com/new](https://github.com/new) задай название, например `list-planner`, и выбери **Public**, если проект должен быть виден всем. Не добавляй README, `.gitignore` и лицензию при создании: первые два уже есть в проекте, лицензию можно выбрать отдельно.

## 2. Подготовь первый коммит

Открой PowerShell и перейди в папку исходников. Для текущего расположения:

```powershell
cd "C:\Users\Kille\Documents\Codex\2026-10-19\new-chat\outputs\daily_planner"
git init -b main
git add .
git status
```

В списке будут исходники и документация. `.venv`, SQLite, логи и результаты сборки исключены через `.gitignore`. Затем:

```powershell
git commit -m "Initial release: List planner"
```

Если Git попросит имя и почту, задай их для этого репозитория и повтори коммит. Вместо примеров укажи свои данные; можно использовать GitHub noreply-адрес из настроек почты аккаунта.

```powershell
git config user.name "YOUR_NAME"
git config user.email "YOUR_EMAIL"
```

## 3. Отправь на GitHub

Замени `USERNAME` и `REPOSITORY` в адресе на владельца и название созданного репозитория:

```powershell
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

При запросе авторизации войди в свой GitHub-аккаунт. Обнови страницу репозитория после успешной отправки.

Порядок соответствует [официальной инструкции GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

## 4. Приложи готовую программу

В репозитории открой **Releases → Draft a new release**, создай тег `v1.0.0` для ветки `main`, заполни название и описание. Прикрепи `ListPlanner-Windows-x64.zip` из папки `outputs` и нажми **Publish release**. Это архив с EXE и инструкцией запуска.

См. [инструкцию GitHub по релизам](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

## 5. Публикуй следующие изменения

В той же папке исходников:

```powershell
git add .
git status
git commit -m "Describe your changes"
git push
```

Если меняется программа, пересобери EXE через `build_exe.bat` и приложи новую сборку к следующему релизу. Для правок одного README пересборка не нужна.
