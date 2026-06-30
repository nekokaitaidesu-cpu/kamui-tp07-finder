@echo off
rem ローカルで手動スキャン＋公開（タスクスケジューラ登録にも使える）
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python finder.py --publish >> scan.log 2>&1
