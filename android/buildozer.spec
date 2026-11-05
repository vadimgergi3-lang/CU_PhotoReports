[app]

# Имя приложения и пакет
title = CONTROL UNION Reports
package.name = fotoreportcu
package.domain = ua.controlunion

# Каталог с исходниками
source.dir = .
source.include_exts = py,png,jpg,jpeg,txt,md,yaml,ttf
source.include_patterns = assets/*

version = 2.0.0

# Зависимости offline-приложения (без Telegram/aiogram)
requirements = python3,kivy==2.3.0,pyjnius,android,pillow,lxml,python-docx,plyer

orientation = portrait
fullscreen = 0

# Android 13+ (min API 33) / target API 34
android.api = 34
android.minapi = 33
android.ndk_api = 24
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

# Разрешения для галереи, камеры и хранения (Android 13+)
android.permissions = INTERNET,ACCESS_NETWORK_STATE,CAMERA,READ_MEDIA_IMAGES,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,POST_NOTIFICATIONS

android.wakelock = False
p4a.branch = master

# Иконка (если есть)
# android.icon.filename = %(source.dir)s/assets/logo.png

[buildozer]
log_level = 2
warn_on_root = 1
