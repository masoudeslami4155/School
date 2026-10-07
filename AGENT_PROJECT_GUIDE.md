# راهنمای فنی عامل‌ها — سامانه مدیریت مدرسه

این فایل نقشهٔ عملیاتی **همین snapshot** پروژه و خلاصهٔ تغییرات را نگه می‌دارد. برای قوانین عمومی عامل، ابتدا `AGENTS.md`؛ برای نصب و استفادهٔ انسانی، `README_MODULAR_FA.md` را بخوانید. در اختلاف میان مستند قدیمی و فایل موجود، وضعیت فایل‌های همین بسته ملاک است.

## ۱. هویت و وضعیت بسته

- نسخهٔ برنامه `4.56` است (`VERSION.txt` و `config.py`).
- برنامه یک سامانهٔ محلی Flask + SQLite با رابط فارسی و منابع CSS/JavaScript/فونت عمدتاً محلی است.
- نقطهٔ ریشهٔ برنامه، همین پوشه‌ای است که `app.py` و `config.py` در آن قرار دارند؛ فایل‌های کد را در ریشهٔ workspace خصوصی عامل نسازید.
- بستهٔ انتشارِ کد-only باید فقط کد، مستندات و assetهای عمومی را داشته باشد؛ دیتابیس واقعی، عکس/مدرک بارگذاری‌شده، پشتیبان، log، کلید نشست، رمز اولیه و مقصد خصوصی backup نباید در آن باشند. آرشیو ورودی این بررسی برخلاف این قاعده شامل داده‌ها و رازهای محلی بود؛ فایل‌های حساس از کپی کاری ایزوله‌شده حذف شدند. آرشیو ورودی را منتشر یا به دیگران ارسال نکنید.
- پوشهٔ `.git/` در آرشیو ارسالی وجود ندارد؛ بنابراین تاریخچهٔ commit، remote با نام `origin`، حساب GitHub و هویت commit از این snapshot قابل تأیید نیستند. `app.py` فعال‌سازی hook را به شکل اختیاری انجام می‌دهد و در نبود Git متوقف نمی‌شود.
- `run.bat` و `tools/setup-hooks.ps1` در این snapshot موجودند. لانچرهای `tools/backup.bat` و `tools/restore.bat`، پوشهٔ `frontend/` و پوشهٔ `.git/` موجود نیستند. برای backup/restore از اسکریپت‌های Python داخل `tools/` استفاده کنید.

## ۲. نقشهٔ فایل‌ها

| مسیر | نقش |
|---|---|
| `app.py` | اجرای محلی، بازکردن مرورگر، پشتیبان آغاز اجرا و تلاش اختیاری برای فعال‌سازی hookها |
| `run.bat` | لانچر ویندوز؛ Python را پیدا می‌کند و `app.py` را اجرا می‌کند |
| `config.py` | نام مدرسه، راز نشست و مسیرهای دیتابیس، بارگذاری، backup و log؛ تنظیمات پیش‌فرض گواهی نیز اینجاست |
| `reset_password_offline.py` | ابزار اضطراری مدیر برای بازنشانی رمز؛ فقط با دیتابیس درست و مجوز مسئول مدرسه اجرا شود |
| `school_app/__init__.py` | ساخت Flask، پیکربندی، log، آماده‌سازی مسیر upload، init دیتابیس و ثبت routeها |
| `school_app/database.py` | اتصال SQLite، ساخت schema، migration، ایجاد حساب اولیه و backup خودکار |
| `school_app/security.py` | نشست، نقش‌ها، فهرست endpointهای مجاز، CSRF، محدودهٔ معلم و audit |
| `school_app/dates.py`, `occasions.py` | تبدیل تاریخ شمسی، قالب تاریخ و مناسبت‌های تقویم آفلاین |
| `school_app/custom_fields.py`, `student_columns.py`, `student_dashboard.py` | فیلدهای سفارشی، جست‌وجو/فیلتر و خلاصهٔ داشبورد، شش حالت نمایش دانش‌آموز با ذخیرهٔ per-user و جدول ستون‌های انتخابی |
| `school_app/user_preferences.py`, `school_app/routes/preferences.py` | تنظیمات امن per-user و شش پالت آمادهٔ روز/شب برای همهٔ صفحه‌ها، همراه فیلدهای دانش‌آموز، داشبورد، قلم، تراکم و سبک؛ route در `/my-settings` |
| `school_app/print_layouts.py`, `report_print_layouts.py`, `student_certificate_layout.py`, `statistics_routes.py` | تنظیمات و منطق چیدمان چاپ سرویس، گزارش، گواهی و آمار |
| `school_app/routes/` | endpointهای هر حوزه؛ routeها با `register(app)` به برنامه متصل می‌شوند |
| `school_app/ai_agent.py` | دستیار هوشمند مدرسه: حلقهٔ ابزار مدل، SQL ابزارها، محدودیت معلم و سازندهٔ پیام مشترک chat/stream |
| `templates/` | صفحه‌های Jinja، بخش‌های چاپی و `partials/` برای اجزای مشترک |
| `static/` | CSS، JavaScript، فونت فارسی، iconها، تصاویر رسمی و کتابخانه‌های محلی |
| `school_app/data/jalali_events.json` | دادهٔ غیرشخصی مناسبت‌های شمسی آفلاین |
| `tools/` | ابزارهای Python برای backup/restore، متن کنسول و نصب hook؛ مقصد backup خصوصی جدا نگه داشته می‌شود |
| `tests/` | اسکریپت‌های آزمون اجرایی؛ آزمون‌ها از دیتابیس و مسیرهای موقت استفاده می‌کنند |
| `AGENTS.md` | قوانین و یادداشت‌های عملیاتی عامل‌های این پروژه |
| `README_MODULAR_FA.md`, `PATCH_NOTES_FA.txt`, `VERSION.txt` | راهنمای کاربر، یادداشت نسخه و شمارهٔ نسخه |

### Routeهای موجود و اتصال آن‌ها

- `school_app/routes/__init__.py` عملاً خالی است؛ فهرست ثبت اصلی در `school_app/__init__.py` و داخل `create_app()` است.
- برای افزودن route module: آن را در import فهرست‌شدهٔ `school_app/__init__.py` بیاورید و `module.register(app)` را در همان چرخهٔ ثبت اضافه کنید.
- حوزه‌های route فعال شامل `auth`, `students`, `teachers`, `attendance`, `finance`, `management`, `calendar`, `reports`, `student_ages`, `contacts`, `data_quality`, `support`, `student_columns`, `preferences`, `meetings`, `student_certificates`, `ai_documents`, `ai_agent`, `print_layouts` و `report_print_layouts` است.
- `statistics_routes.py` تابع‌های آمار را فراهم می‌کند و `routes/management.py` آن را وارد می‌کند؛ خودش route module مستقل نیست.
- `routes/attendance_backup.py` در درخت هست اما در لیست ثبت `create_app()` ثبت نشده؛ پیش از تغییر یا فعال‌کردنش وابستگی‌ها و تفاوتش با `attendance.py` را بررسی کنید.

## ۳. چرخهٔ اجرا و تنظیمات

```powershell
py -m pip install -r requirements.txt
py app.py
```

روی محیط‌های Unix:

```bash
python -m pip install -r requirements.txt
python app.py
```

سپس `http://127.0.0.1:5000` باز می‌شود؛ پورت با `PORT` قابل تغییر است. برنامهٔ دسکتاپی اختیاری `pywebview` است و برای اجرای معمول لازم نیست.

**نکتهٔ مهم آزمون/ایمنی:** import کردن `school_app` اپ را می‌سازد؛ `create_app()` همان موقع log و upload directory را می‌سازد و در app context backup و init دیتابیس را اجرا می‌کند. بنابراین پیش از import در آزمون‌ها یا ابزارهای یک‌باره، مسیرهای جداگانهٔ زیر را تنظیم کنید:

- `DATABASE_PATH`: دیتابیس SQLite؛ مقدار پیش‌فرض `school.db` در ریشهٔ پروژه است.
- `BACKUP_DIR`: پوشهٔ backup خودکار و دستی؛ پیش‌فرض `backups/`.
- `LOG_DIR`: پوشهٔ لاگ؛ پیش‌فرض `logs/`.
- `UPLOAD_FOLDER`: عکس‌ها و اسناد؛ پیش‌فرض `static/uploads/`.
- `SECRET_KEY`: راز نشست؛ اگر تعیین نشود، `.secret_key` محلی ساخته می‌شود.
- `SCHOOL_NAME`, `PROGRAMMER_NAME`: عنوان‌های پیش‌فرض چاپ/رابط.
- `CERTIFICATE_SCHOOL_NAME`, `CERTIFICATE_SCHOOL_CODE`, `CERTIFICATE_EDUCATION_PERIOD`, `CERTIFICATE_STUDY_PROGRAM`, `CERTIFICATE_DIRECTOR`: پیش‌فرض‌های فرم گواهی؛ مقدار فرم قبل از چاپ قابل ویرایش است.
- `ADMIN_PERSONNEL_NUMBER`: شناسهٔ پیش‌فرض مدیر نخستین اجرا.

بدون دیتابیس، اجرای نخست schema خالی می‌سازد و در صورت ساخت مدیر اولیه، رمز موقت را در `initial_credentials.txt` می‌نویسد. آن فایل راز محلی است و نباید برای دیگران ارسال شود. دریافت‌کنندهٔ ZIP کد-only داده‌های مدرسه یا حساب‌های فعلی را دریافت نمی‌کند.

## ۴. معماری داده و امنیت

- داده‌ها با SQLite و SQL پارامتری مدیریت می‌شوند؛ `get_db()` در `school_app/database.py` نقطهٔ اتصال معمول است. پیش از schema change، migration و backup را بررسی کنید.
- بخش‌های اصلی schema شامل دانش‌آموزان، کاربران/کارکنان، حضور، سرویس/مالی، تقویم و کارها، تنظیمات کاربر، فیلدهای سفارشی و audit است.
- هیچ تستی را با تنظیمات پیش‌فرض روی `school.db` واقعی اجرا نکنید. برای هر تست مسیرهای موقت را **قبل از import اپ** تنظیم کنید. از دیتابیس نمونهٔ ZIP به‌عنوان دیتابیس واقعی استفاده نکنید.
- نقش‌ها `admin`، `manager` و `teacher` هستند. دسترسی endpoint در `security.py` تعیین می‌شود؛ هر POST احراز هویت‌شده باید CSRF معتبر داشته باشد. teacher-scope در query/data-layer enforce شود و فقط به پنهان‌کردن UI تکیه نشود.
- `static/uploads/` می‌تواند تصویر دانش‌آموز یا مدرک مشاوره داشته باشد؛ `school.db`، فایل‌های `-wal/-shm`، `initial_credentials.txt`، `.secret_key`، `backups/`, `logs/`, `offline_backups/` و `tools/backup_target.txt` داده/راز محلی‌اند.
- `.gitignore` فهرست حساسیت‌های Git را دارد؛ برای ZIP هم به `.gitignore` به‌تنهایی تکیه نکنید و فهرست حذف را صریح در دستور بسته‌بندی اعمال کنید.

## ۵. تغییرات ثبت‌شده در این کار

### گواهی اشتغال به تحصیل

- مسیر `/student-certificate` در `school_app/routes/student_certificates.py` دستی یا از پروندهٔ دانش‌آموز فعال، گواهی را می‌سازد؛ گواهی در دیتابیس ذخیره نمی‌شود.
- دسترسی `student_certificate` برای مدیر/معاون (`admin`/`manager`) است؛ teacher باید 403 بگیرد.
- پیوند مستقل «صدور گواهی اشتغال به تحصیل» در ناوبری اصلی برای `admin` و `manager` است. از فرم گواهی نیز دکمهٔ «تنظیم چیدمان چاپ» به استودیو می‌رود.
- قالب `templates/print_student_certificate.html` صفحهٔ A3 را در هر دو جهت می‌سازد. جهت عمودی همان قاب افقی در نیمهٔ بالایی صفحه و جهت افقی قاب بزرگ‌تر را دارد.
- استودیوی گواهی در `/report-print-layouts?document=student_certificate` است. می‌توان هر یک از ۲۵ جزء (متن، فیلد، عکس و QR) را با drag ماوس یا مختصات X/Y جابه‌جا کرد؛ عرض، ارتفاع و اندازهٔ قلم نیز برای جزء انتخاب‌شده قابل ویرایش است. کلیدهای جهت‌دار برای جابه‌جایی ریز کار می‌کنند.
- مدل allowlist چیدمان در `school_app/student_certificate_layout.py` است. تنظیم per-user در `app_settings` با کلید `student_certificate_layout:<user_id>` ذخیره می‌شود؛ sanitize مختصات/ابعاد را به صفحه محدود می‌کند. این تنظیمات به اطلاعات دانش‌آموز یا متن فرم دست نمی‌زنند.
- `templates/partials/student_certificate_artwork.html` همان artwork را برای پیش‌نمایش و چاپ واقعی استفاده می‌کند؛ قواعد اندازه/چاپ در `static/student_certificate_print.css`، UI در `templates/student_certificate_studio.html` و تعامل drag در `static/student_certificate_studio.js` و `static/student_certificate_studio.css` است. چاپ از تنظیمات ذخیره‌شدهٔ کاربر جاری استفاده می‌کند.
- الگوی گواهی در استودیو فقط برای `admin` و `manager` نمایش داده می‌شود؛ نقش teacher در route این سند پاسخ ۴۰۳ می‌گیرد.
- نمونهٔ ارسالی تاریخ تولد، تاریخ تقاضا و مقصد «بهزیستی» را داشت؛ پس برخلاف نسخهٔ پیشین این سه مورد در خروجی فعلی وجود دارند. فرم می‌تواند آن‌ها را ویرایش کند.
- schema ستون مستقل کد ملی دانش‌آموز ندارد؛ یک مقدار قابل ویرایش از `students.student_id_serial` برای هر دو برچسب کد ملی و شمارهٔ شناسنامه استفاده می‌شود.
- عکس پرونده اگر در `static/uploads/` باشد نمایش داده می‌شود. عکس دستی JPG/PNG تا ۲ MiB به‌صورت data URI فقط در پاسخ چاپ قرار می‌گیرد و روی دیسک/دیتابیس ذخیره نمی‌شود.
- QR به‌صورت SVG آفلاین است و فقط نام، کد دانش‌آموزی، پایه، کلاس و سال تحصیلی را دارد؛ کد ملی/تاریخ تولد در payload نیست. QR گواهی را به‌صورت آنلاین اعتبارسنجی نمی‌کند.
- شمارهٔ گواهی از schema تولید نمی‌شود و دستی وارد می‌شود. نام کوتاه/کد مدرسه، دوره، رشته و نام مدیر از پیکربندی قابل تنظیم و در فرم قابل اصلاح‌اند.
- فونت نمونه در PDF `Wyekan` بود؛ قالب اگر این قلم روی ویندوز نصب باشد از آن استفاده می‌کند، در غیر این صورت Vazirmatn/Tahoma fallback خواهد شد.
- آزمون‌های اختصاصی `tests/student_certificate_test.py` و `tests/print_studio_routes_test.py` با دیتابیس موقت، ورود دستی/خودکار، دو شناسهٔ مشترک، عکس، QR، ناوبری، ذخیره/بازنشانی تنظیمات per-user، sanitize، چاپ A3 افقی/عمودی و مرز نقش‌ها را بررسی می‌کنند.

### طراح هوشمند اسناد چاپی

- صفحهٔ `/ai-documents` برای مدیر و معاون و تنظیم اتصال `/settings/ai-documents` فقط برای مدیر است. انواع خروجی: نامه، دعوت‌نامه، کارت و رسید سرویس؛ پیش‌نمایش در iframe محدودشده و چاپ با اندازهٔ انتخابی A4 عمودی/افقی، A5 یا کارت انجام می‌شود.
- route و منطق داده در `school_app/routes/ai_documents.py` و `school_app/ai_documents.py`؛ UI در `templates/ai_documents.html`, `templates/ai_documents_settings.html` و فایل‌های `static/ai_documents.css`, `static/ai_documents.js`, `static/ai_documents_settings.js` است. endpointهای جدید در `security.py` فقط admin/manager را مجاز می‌کنند.
- Ollama محلی از API سازگار OpenAI در `http://127.0.0.1:11434/v1` استفاده می‌کند. دو provider اینترنتی پشتیبانی می‌شوند: API سازگار با OpenAI و Google Gemini (endpoint سازگار با OpenAI روی `https://generativelanguage.googleapis.com/v1beta/openai` و مدل پیش‌فرض `gemini-2.0-flash`). اتصال اینترنتی باید HTTPS و OpenAI-compatible باشد؛ پیش از هر تولید آنلاین، کاربر باید صریحاً اجازه بدهد. تنظیم provider و مدل در `app_settings` قرار می‌گیرد؛ کلید API با Fernet و کلید مشتق‌شده از `SECRET_KEY` رمز می‌شود. پس از چرخاندن `SECRET_KEY`، کلید remote باید دوباره وارد شود.
- دادهٔ model حداکثر ۱۲ دانش‌آموز را می‌پذیرد. فقط نام، پایه، کلاس، نام مدرسه و سال/تاریخ لازم فرستاده می‌شود؛ برای نامه/دعوت‌نامه نام پدر هم افزوده می‌شود. اطلاعات تماس، کد ملی، سلامت و عکس در payload نیستند. متن brief کاربر نیز به provider انتخاب‌شده فرستاده می‌شود.
- رسید در هر بار فقط یک دانش‌آموز دارد؛ آخرین ردیف سرویس ماهانه با ترتیب سال و ماه تحصیلی انتخاب می‌شود و مبلغ مصوب/پرداختی/مانده فقط از پایگاه‌داده می‌آیند. مدل فقط placeholder می‌سازد و مبلغ‌ها را محاسبه نمی‌کند.
- پاسخ مدل فقط fragment HTML است؛ `bleach` و `CSSSanitizer` با allowlist آن را پاک‌سازی می‌کنند، placeholderهای ناشناخته/مفقود یا عدد مالی آزاد رد می‌شوند و داده‌ها هنگام جایگزینی HTML-escape می‌شوند. به CSS/اسکریپت/منبع بیرونی مدل اجازهٔ اجرا داده نمی‌شود.
- «ساخت نامهٔ آماده» نامهٔ اداری را سروری و بدون نیاز به مدل می‌سازد: طرح مشترک در `templates/partials/ai_letter_artwork.html` است و `school_app/ai_documents.py:generate_letter_document` آن را با چیدمان ذخیره‌شدهٔ کاربر می‌آمیزد.
- نامهٔ تولیدشده در استودیوی طراحی قابل ویرایش است: `/report-print-layouts?document=ai_letter` اجزای نامه (تاریخ، نام مدرسه، موضوع، متن، امضا و …) را می‌توان جابه‌جا و اندازه‌گذاری کرد. چیدمان هر کاربر در `app_settings` با کلید `ai_letter_layout:<user_id>` می‌نشیند (`school_app/ai_letter_layout.py`) و پس از ذخیره روی پیش‌نمایش `/ai-letter-preview` و نامه‌های تولیدشده اعمال می‌شود. جهت، حاشیه و قلم هم قابل تنظیم است و مقدارها در بازهٔ مجاز گرفته می‌شوند.
- الگوهای نامه: سه الگوی پیش‌فرض (تذکر رسمی، دعوت‌نامه، نامهٔ معرفی) با چیدمان مخصوص خود در `TEMPLATE_PRESETS` هستند و کاربر می‌تواند در استودیو الگوی شخصی (حداکثر ۱۲ مورد، کلید `ai_letter_templates:<user_id>`) ذخیره، بارگذاری یا حذف کند. الگوی انتخاب‌شده در «ساخت نامهٔ آماده» (`/ai-documents/generate-letter` با فیلد `template`) اعمال می‌شود و کلیدهای پیش‌فرض محفوظ و غیرقابل حذف‌اند. آزمون `tests/ai_letter_templates_test.py` این گردش کار را می‌سنجد.
- آزمون `tests/ai_documents_test.py` نقش‌ها، CSRF، رمزگذاری کلید، رضایت remote، محدودیت فیلدها، رسید و sanitize را با دیتابیس موقت و بدون تماس واقعی با مدل می‌سنجد؛ `tests/print_studio_routes_test.py` بارگذاری، ذخیره و بازنشانی استودیوی نامه را بررسی می‌کند و `tests/ai_letter_templates_test.py` الگوهای پیش‌فرض و شخصی نامه را.

#### انتخاب سرویس و مدل در صفحهٔ طراحی (نسخهٔ ۴.۵۲)

- پیش از این تغییر، provider فقط در `/settings/ai-documents` (admin) قابل تغییر بود و صفحهٔ `/ai-documents` فقط یک کارت وضعیت خواندنی داشت؛ حالا همان صفحه کادر انتخاب سرویس و مدل دارد.
- `provider_choices` فقط سرویس‌های واقعاً قابل استفاده را فهرست می‌کند: Ollama محلی و provider اینترنتی ثبت‌شده (اگر کامل باشد). انتخاب کاربر با `ai_documents:provider_selection:<user_id>` در `app_settings` ذخیره می‌شود و **تنظیم ثبت‌شدهٔ مدیر را تغییر نمی‌دهد**.
- `ollama_status` مدل‌های نصب‌شده را از `/api/tags` می‌خواند و «آفلاین بودن» را از «بدون مدل» جدا می‌کند؛ `list_ollama_models` پوستهٔ نازک روی همان است و برای endpoint قدیمی admin باقی مانده.
- مدل محلی فقط وقتی ذخیره می‌شود که در فهرست واقعی Ollama باشد؛ در مسیر تولید فقط قالب نام بررسی می‌شود تا هر درخواست یک تماس شبکهٔ اضافه نداشته باشد.
- `effective_private_provider_config` در مسیر محلی کلید ذخیره‌شده را رمزگشایی نمی‌کند؛ پس چرخاندن `SECRET_KEY` تولید آفلاین را نمی‌شکند. دروازهٔ رضایت اینترنتی (`allow_external_data`) حالا به سرویس مؤثر گره خورده است، نه به سرویس ثبت‌شده.
- endpointهای تازه `ai_documents_models` (GET) و `ai_documents_select_provider` (POST) در `MANAGER_ENDPOINTS` و `PERMISSION_LABELS` هستند؛ اولی URL را از درخواست نمی‌گیرد (فقط نشانی محلی)، پس proxy باز نمی‌شود.
- دکمهٔ «ذخیرهٔ مدل» و کادر تاشوی «ثبت اتصال سرویس اینترنتی» روی همین صفحه هستند تا نشانی و کلید API یک‌بار وارد و ذخیره شوند. کادر فقط برای `admin` رندر می‌شود و `ai_documents_save_connection` (POST) در `ADMIN_ENDPOINTS` است؛ همان مسیر امن `save_provider_config` با `auto_backup()` و `audit` اجرا می‌شود و پاسخ، فهرست تازهٔ سرویس‌ها را برمی‌گرداند تا انتخاب بدون بارگذاری دوبارهٔ صفحه انجام شود.
- دستیار هوشمند (`school_app/ai_agent.py:_load_provider_config`) همین انتخاب per-user را می‌خواند تا مدلِ انتخابی کاربر در هر دو بخش یکی باشد.
- نکتهٔ تست: نام `school_app.ai_documents` در فضای نام پکیج با ماژول `school_app.routes.ai_documents` پوشانده می‌شود؛ برای patch کردن `ollama_status` باید از `patch.object(importlib.import_module('school_app.ai_documents'), ...)` استفاده کرد.

### دستیار هوشمند مدرسه (`/ai-agent`)
- مسیر `/ai-agent` (صفحه) و `/ai-agent/chat` و `/ai-agent/stream` در `school_app/routes/ai_agent.py` ثبت شده‌اند؛ منطق حلقه و ابزار در `school_app/ai_agent.py` و UI در `templates/ai_agent.html`, `static/ai_agent.css` و `static/ai_agent.js` است. هر سه endpoint در `MANAGER_ENDPOINTS` هستند، پس فقط `admin` و `manager` مجازند.
- تابع route صفحه همان provider ذخیره‌شدهٔ اسناد را با `public_provider_config` می‌خواند و به قالب می‌دهد؛ قالب وضعیت واقعی را نشان می‌دهد: «متصل به <provider> — <model>» با نقطهٔ سبز در حالت تنظیم‌شده، و «هوش مصنوعی هنوز تنظیم نشده است» با بنر هشدار و ورودی/دکمهٔ غیرفعال در حالت تنظیم‌نشده. وضعیت قبلی (همیشه «آنلاین») حذف شد.
- حلقهٔ ابزار پاسخ خام دستیار را از `request_chat_message` می‌گیرد و `content` و `tool_calls` را جدا می‌خواند؛ این تابع در `school_app/ai_documents.py` افزوده شده و `request_chat_completion` اکنون پوستهٔ نازکی روی آن است. سقف حلقه ۸ دور ابزار است و خطای provider به‌صورت `AIProviderError` به کاربر برگردانده می‌شود.
- ابزار `get_school_summary` تنها ابزار شمارش کلی است: `total_students` و همهٔ تفکیک‌ها روی یک جمعیت حساب می‌شوند (`scope`: `all` پیش‌فرض، `active` برای فقط فعال‌ها) و `by_status` همیشه سرشماری همهٔ وضعیت‌ها با برچسب روشن است. تعریف «فعال» همان `school_app/statistics_routes.py::_status_sql` است (`فعال` یا NULL یا رشتهٔ خالی). `get_statistics` عمداً عدد کل نمی‌دهد و در description خودش به `get_school_summary` ارجاع می‌دهد.
- دو مسیر `run_agent` و `stream_agent_event` از `_ToolCallLedger` استفاده می‌کنند: فراخوانی با آرگومان یکسان دوباره اجرا نمی‌شود، نتیجهٔ قبلی با یادداشت «تکراری» برگردانده می‌شود و پس از `_REPEAT_LIMIT = 3` تکرار حلقه با `_STUCK_MESSAGE` («نتیجهٔ قطعی نرسیدم» + ارجاع به صفحهٔ آمار) زودتر بسته می‌شود. `execute_tool` آرگومان‌های `required` و مقدار `scope` را پیش از باز کردن دیتابیس اعتبارسنجی می‌کند تا به مدل خطای روشن برگردد، نه جدول خالی.
- دسترسی پایگاه داده: `describe_database` (فهرست جدول/ستون) و `query_database` (یک SELECT/WITH با اتصال `mode=ro`؛ اگر WAL اجازه نداد، همان گارد سخت‌گیرانه جلوی نوشتن را می‌گیرد). `_guard_sql` یک دستور را می‌پذیرد و جدول‌های `users`/`app_settings`/`audit_log`/`sqlite_*`، دستور‌های DDL، `;` اضافی و `UPDATE/DELETE` بدون `WHERE` را رد می‌کند. `params` با `?` پشتیبانی می‌شود و نتیجه به ۲۰۰ ردیف/۹۰۰۰ نویسه محدود است.
- نوشتن دو مرحله‌ای است: `propose_database_change` هیچ چیزی اجرا نمی‌کند و پیشنهاد را با کلید `ai_agent:pending_change:<user_id>` در `app_settings` می‌گذارد؛ endpoint `ai_agent_apply_change` (POST، در `MANAGER_ENDPOINTS`) پس از بررسی دوبارهٔ SQL، `auto_backup()` و ثبت `audit_log`، آن را اجرا و پیشنهاد را پاک می‌کند. دلیل نگه‌داری در دیتابیس و نه نشست: پاسخ stream پیش از اجرای بدنه پاسخ، کوکی نشست را می‌فرستد و تغییرات نشست ذخیره نمی‌شود.
- گزارش چاپی: `generate_report_html` در هر پاسخ فقط یک‌بار اجرا می‌شود (`_REPORT_ONCE_NOTE`) و نتیجهٔ پاکسازی‌شدهٔ خودِ سرور با رویداد `report` (stream) یا کلید `reports` (chat) به صفحه می‌رسد؛ کارت `.agent-report` با دکمهٔ «چاپ جدول» از یک iframe جدا و CSS مخصوص A4 چاپ می‌شود. کارت `pending_change` هم دکمهٔ «تأیید و اجرا» دارد.
- نکتهٔ نمایشی: `app.css` برای همهٔ `table` مقدار `min-width:720px` و `liquid_glass_magma.css` با `:where(table){color:...!important}` رنگ جدول را عوض می‌کند؛ قواعد کارت گزارش با `!important` و `min-width:0` داخل حباب پیام محدود شده‌اند.
- هر دو مسیر `run_agent` (chat) و `stream_agent_event` از یک message builder مشترک استفاده می‌کنند تا system prompt در هر دو مسیر ارسال شود و system prompt تزریق‌شده از سمت کلاینت فیلتر گردد.
- SQL ابزارها با schema واقعی هم‌راستا شده است: حضور از جدول `attendance_students` (`a.date`/`a.status`)، ماه از `substr(a.date,6,2)`، و محدودهٔ معلم با `personnel_number` روی دانش‌آموزان، نه `id` کاربر. ترتیب ماه تحصیلی از `ACADEMIC_MONTHS` و `month_order_sql()` در `school_app/dates.py` می‌آید و مسیر رسید در اسناد چاپی هم به همان منتقل شد.
- محدودیت باز: route صفحه نقش `teacher` را می‌پذیرد و لایهٔ ابزار scoping معلم را دارد، اما `security.TEACHER_ENDPOINTS` نام `ai_agent` را ندارد؛ پس معلم پیش از اجرای route پاسخ ۴۰۳ می‌گیرد. این رفتار عمداً در `tests/ai_agent_test.py` ثبت شده و allowlist دست‌نخورده مانده است.
- محدودیت باز: برخلاف اسناد چاپی، دستیار دروازهٔ رضایت `allow_external_data` برای API اینترنتی ندارد؛ افزودن آن به UI نیاز دارد و انجام نشد.
- توصیهٔ عملیاتی: مدل باید tool-capable باشد. مثلاً `gemma3:4b` روی Ollama پاسخ `does not support tools` می‌دهد و انتخاب آن دستیار را به خطای provider می‌برد؛ از مدل‌هایی مثل `gpt-oss:20b` یا `deepseek-r1:14b` استفاده کنید.
- آزمون `tests/ai_agent_test.py` با دیتابیس موقت و پاسخ ساختگی مدل، حلقهٔ ابزار، مسیر stream، هم‌راستایی schema، وضعیت صفحه (۶۷ تست)، مرز دسترسی نقش‌ها، توقف روی فراخوانی تکراری، گارد SQL، پنهان‌ماندن کلیدها و مسیر پیشنهاد→تأیید→اجرا را می‌سنجد. در بررسی این snapshot هیچ دیتابیس واقعی یا سرویس مدل زنده‌ای استفاده نشد.

### استودیو چاپ

- قالب‌های استودیو در `templates/print_studio.html`, `templates/student_certificate_studio.html`, `templates/print_wall_cards.html` و `templates/report_print_layouts.html` قرار دارند؛ route/modelهای مرتبط `routes/print_layouts.py`, `routes/report_print_layouts.py`, `school_app/print_layouts.py`, `school_app/report_print_layouts.py` و `school_app/student_certificate_layout.py` هستند.
- تغییرات پیشین این workspace شامل کارت دیواری دانش‌آموز و راهنمای چاپی فیلترهاست؛ state چیدمان‌های استودیو در `app_settings` per-user ذخیره می‌شود. در این کار دادهٔ زندهٔ تنظیمات تغییر داده نشد.
- برای الگوهای گزارش نیز اجزای سربرگ، پابرگ، خلاصه/جدول و بخش‌های قابل پشتیبانی در پیش‌نمایش با ماوس جابه‌جا یا تغییر اندازه می‌شوند؛ تنظیمات X/Y و مقیاس ذخیره‌شده در خروجی چاپ واقعی اعمال می‌شود. چاپ حضور دانش‌آموزان و معلمان جهت و بخش‌های ذخیره‌شده را مستقل از query می‌خواند.
- در مجموع ۱۱ الگوی استودیو وجود دارد: سه الگوی سرویس، هفت الگوی گزارش و گواهی A3. تست مسیر استودیو هم markup پابرگ گزارش را از پیش‌نمایش سرویس جداگانه بررسی می‌کند.
- آزمون استودیو `tests/print_studio_routes_test.py` و آزمون مدل/گزارش‌ها باید بعد از تغییرات قالب/چیدمان اجرا شوند.

### تنظیمات شخصی رابط و داشبورد (نسخهٔ ۴.۵۶؛ پایهٔ قبلی ۴.۵۵)

- جست‌وجوی اصلی از ابتدای داشبورد برداشته شده، نه حذف؛ فرم در `templates/index.html` داخل `<details>` بستهٔ `dashboard-search-section` پس از بخش‌های خلاصه قرار دارد و با فیلتر فعال خودکار باز می‌شود.
- پیوند تنظیمات مشترک به `/my-settings` (`ui_preferences`) برای `admin`، `manager` و `teacher` در `COMMON_ENDPOINTS` است. گزینه‌ها با کلید `ui_preferences:<user_id>` در `app_settings` ذخیره می‌شوند؛ شش پالت دوحالتهٔ اقیانوس/جنگل/یاس/رز/کهربا/خاکستری یا رنگ‌های دستی allowlist شده‌اند؛ ورودی دستی فقط `#RRGGBB` است.
- همهٔ صفحه‌های وابسته به `base.html` پس از CSS اختصاصی، `static/user_preferences.css` را می‌گیرند. صفحه‌های مستقل مانند ورود، بازیابی، حذف و پیش‌نمایش‌های چاپ از `templates/partials/user_palette_head.html` استفاده می‌کنند؛ CSS پالت در پیش‌نمایش مستقل فقط روی `screen` است تا طراحی چاپ فیزیکی تغییر نکند.
- فیلدهای کارت، ستون‌های جدول و فیلدهای کارت موبایل سه انتخاب مستقل‌اند؛ نام در هر سه همیشه حفظ می‌شود. موبایل در عرض ۷۲۰ پیکسل کارت خلاصه نشان می‌دهد، حتی اگر حالت رومیزی روی `table` باشد؛ ستون‌های انتخاب/اقدامات همچنان جدا هستند.
- شش حالت `student_card_view:<user_id>` هنوز نگهداری می‌شوند اما انتخابگر از `templates/index.html` حذف شده و در تنظیمات زیر `student_view` قابل تغییر است. route قدیمی `/student-view` برای سازگاری و آزمون باقی است.
- الگوهای `simple`, `teacher`, `management` فقط چیدمان/فیلدها/حالت فهرست را عوض می‌کنند و پالت روز/شب کاربر را حفظ می‌کنند؛ reset بخشی و بازنشانی کامل هر دو CSRF دارند.
- کارت‌های `quick_actions`, `overview`, `reminders`, `data_quality` قابل خاموش‌کردن‌اند؛ فهرست اصلی و فیلترها خاموش نمی‌شوند و `urgent_count` بخش یادآور فوری را حتی اگر `reminders` خاموش باشد نگه می‌دارد.
- اقدام‌های سریع در `QUICK_ACTIONS` تعریف شده‌اند، اما UI فقط خروجی `available_quick_actions(role, _session_endpoints(role), selected)` را می‌سازد. `/my-settings` گزینه‌های نشست فعلی را می‌گیرد و `_finish_save` انتخاب را به همان allowlist محدود می‌کند؛ اعتبارسنجی route در `security.py` مرجع نهایی است و تنظیمات رابط مجوز را تغییر نمی‌دهد.
- ترجیحات جدول در `user_preferences.py` شامل `student_table_order`, `student_table_pinned`, `student_table_column_widths`, `student_table_sort`, `student_table_sort_direction` و `student_table_page_size` هستند. sanitizer ترتیب را کامل می‌کند، نام را اول/ثابت نگه می‌دارد، حداکثر سه ستون ثابت و عرض/مرتب‌سازی/تعداد ردیف را allowlist می‌کند. بازنشانی `student_table_fields` همهٔ این کلیدها را هم برمی‌گرداند.
- `templates/index.html` دادهٔ مرتب‌سازی را با متن escaped در `data-sort-*` می‌گذارد؛ `static/index.js` مرتب‌سازی طبیعی فارسی، صفحه‌بندی، ادغام با جست‌وجوی سریع و offset ستون‌های sticky را انجام می‌دهد. ستون‌های پین‌شده جلوتر از بقیه قرار می‌گیرند؛ CSS چاپ sticky را خنثی می‌کند و toolbar چاپ نمی‌شود.
- `templates/user_preferences.html` ترتیب را با دکمه‌های بالا/پایین تغییر می‌دهد؛ چون hidden/checkboxها همراه row در DOM جابه‌جا می‌شوند، ترتیب POST با ترتیب دیداری یکی است. `static/user_preferences.js` محدودیت سه ستون و وابستگی pin به ستون انتخاب‌شده را client-side راهنمایی می‌کند؛ سرور دوباره اعتبارسنجی می‌کند.
- `static/user_preferences.css` لایهٔ رنگ سراسری است: توکن‌های `--primary`, `--surface`, `--ink`, `--line`، پس‌زمینه، فرم‌ها، ناوبری، جدول‌ها و کارت‌های مشترک را روی همهٔ صفحه‌های نمایش اعمال می‌کند. `static/user_preferences.js` پیش‌نمایش رنگ/کنتراست و تشخیص پالت شخصی را انجام می‌دهد؛ `static/user_accessibility.js` اندازهٔ متن را اعمال و پیش از چاپ اندازه‌ها را بازیابی می‌کند. پیش‌نمایش‌های مستقل تم را روی نمایشگر می‌گیرند، نه چاپ فیزیکی.
- `tests/user_preferences_test.py` و `tests/student_view_test.py` با دیتابیس موقت ذخیره/جداسازی حساب‌ها، هر سه نقش و مجوزهای سفارشی، انتخاب/ترتیب اقدام‌های سریع بدون اعطای دسترسی، ترتیب/عرض/pin/مرتب‌سازی/صفحه‌بندی جدول، بازنشانی بخشی، ستون‌های مستقل، شش پالت با کنتراست و پوشش رنگ سراسری، چاپ، موبایل، دسترس‌پذیری، sanitizer و CSRF را بررسی می‌کنند.

## ۶. تست و بررسی

وابستگی‌های لازم در `requirements.txt` هستند. ابتدا از ریشهٔ پروژه اجرا کنید:

```bash
python -m pip install -r requirements.txt
```

همهٔ اسکریپت‌های آزمون این پروژه را به‌ترتیب و از ریشه اجرا کنید؛ آن‌ها از دیتابیس‌های موقت/درون‌حافظه‌ای استفاده می‌کنند. آزمون‌ها را هم‌زمان اجرا نکنید، چون چند اسکریپت فایل موقت `initial_credentials.txt` را پاک‌سازی می‌کنند.

```bash
python tests/smoke_get_routes.py --brief
python tests/contact_book_settings_test.py --brief
python tests/print_layouts_test.py
python tests/report_print_layouts_test.py
python tests/statistics_print_test.py
python tests/print_studio_routes_test.py
python tests/student_certificate_test.py
python tests/ai_documents_test.py
python tests/ai_agent_test.py
python tests/attendance_quick_test.py
python tests/ai_letter_templates_test.py
python tests/ai_parser_resilience_check.py
python tests/ai_persistence_check.py
python tests/student_view_test.py
python tests/user_preferences_test.py
python -m compileall -q school_app tools tests
find static -type f -name '*.js' -print0 | xargs -0 -n1 node --check
```

`tests/student_view_test.py` شش حالت پیش‌فرض (که حالا فقط در صفحهٔ تنظیمات انتخاب می‌شوند)، حذف کنترل از `index`، فیلدهای مخفی، نمای کارت در موبایل، پنل جست‌وجوی تاشو، یادآور و اعلان اختیاری را بررسی می‌کند. `tests/user_preferences_test.py` نقش‌ها، جداسازی per-user، فیلدهای مستقل کارت/جدول/موبایل، الگوها، بازنشانی بخشی، دو پالت، بررسی کنتراست، متن بزرگ، line spacing و reduced motion را پوشش می‌دهد.

نتیجهٔ بررسی ایزولهٔ این کپی در ۷ اکتبر ۲۰۲۶ با Python 3.13.14: هر ۱۵ اسکریپت آزمون موفق شدند؛ اسموک‌تست ۲۳۷ درخواست GET را با نقش‌های `admin`، `manager` و `teacher` بدون خطای ۵۰۰ اجرا کرد؛ آزمون دفترچه تلفن ۲۸ بررسی و آزمون دستیار هوشمند ۶۷ تست را گذراند. نحو ۶۵ فایل Python و ۲۵ فایل JavaScript نیز بررسی شد و خطایی نداشت. این بررسی به دیتابیس واقعی، تصاویر دانش‌آموزان یا سرویس مدل زنده وصل نشد.

## ۷. Backup و تغییرات داده

- فایل‌های در دسترس در `tools/`: `backup_center.py`, `offline_backup.py`, `restore_center.py`, `install_hooks.py`, `setup-hooks.ps1`, `console_text.py` و `git-hooks/`.
- `tools/setup-hooks.ps1` موجود است؛ لانچرهای `tools/backup.bat` و `tools/restore.bat` و فایل خصوصی `tools/backup_target.txt` در این snapshot نیستند. برای backup/restore از اسکریپت‌های Python استفاده کنید؛ پیش از عملیات واقعی، `python tools/backup_center.py --help`, `python tools/offline_backup.py --help` و `python tools/restore_center.py --help` را از ریشه بررسی کنید.
- ZIP کد-only با backup کامل یکی نیست. برای انتقال اطلاعات واقعی باید مسئول مجاز جداگانه ابزار offline backup را بررسی کند، فایل رمز را جدا نگه دارد و مقصد را امن کند؛ خروجی دیتادار را در گفت‌وگو یا ZIP عمومی نفرستید.
- تغییرات migration یا حذف فایل‌ها را روی دادهٔ زنده آزمایش نکنید. این کپی ایزوله فاقد `school.db` و `static/uploads/` است؛ روی نصب واقعی این فایل‌ها را پاک یا جایگزین نکنید.

## ۸. بستهٔ ZIP این تحویل

فهرست ZIP از ریشهٔ پروژه ساخته می‌شود و خود این راهنما، `AGENTS.md`, `README_MODULAR_FA.md`, کد، assets محلی و تست‌ها را دارد. عمداً این مسیرها حذف می‌شوند:

```text
school.db, *.db, *.db-wal, *.db-shm, *.db-journal
.secret_key, initial_credentials.txt, .env*, *.key, *.pem
backups/, offline_backups/, logs/, static/uploads/, tools/backup_target.txt
_preview_server.py, test_gemini.py, test_gemini_connect.py
.freebuff/, .git/, __pycache__/, *.py[cod], .pytest_cache/, .mypy_cache/, .ruff_cache/
.venv/, venv/, env/, *.zip
```

این مشخصات برای ZIP کد-only است؛ آرشیو اصلی ارسالی برای بررسی آن‌ها را رعایت نمی‌کرد و نباید منتشر شود. کپی ایزولهٔ بررسی‌شده، پس از حذف فایل‌های حساس، با فهرست حذف بالا هماهنگ است. هیچ ZIP را روی پروژهٔ واقعی extract نکنید؛ ابتدا در پوشهٔ تازه استخراج و بررسی کنید. برای اجرای برنامه، نصب وابستگی و `python app.py` کافی است؛ دیتابیس خالی و مسیرهای محلی در اولین اجرا ساخته می‌شوند. اگر آرشیو اصلی را خارج از محیط مورد اعتماد به اشتراک گذاشته‌اید، کلید نشست و رمز مدیر اولیه را عوض کنید.


## به‌روزرسانی ۴.۵۷
نسخهٔ ۴.۵۷ — گرادیانت سراسری و گواهی A4
- پس‌زمینهٔ چندلایهٔ گرادیانت از رنگ‌های پالت روز/شب و رنگ‌های شخصی ساخته می‌شود؛ هدر و سایدبار نیز از همان رنگ‌ها استفاده می‌کنند. قواعد جدید فقط screen هستند.
- گواهی به‌صورت پیش‌فرض A4 با قاب تمام‌صفحه، چیدمان دو ستونی و قلم خواناتر ساخته می‌شود؛ A3 همچنان قابل انتخاب است.
- استودیو: اندازهٔ کاغذ، مقیاس قلم، حاشیهٔ قاب، ضخامت قاب و بازنشانی یک جزء، در کنار جابه‌جایی و تغییر اندازهٔ اجزا.
- مختصات چیدمان‌های قدیمی حفظ می‌شود و قلم‌های قدیمی هنگام بارگذاری بزرگ‌تر می‌شوند؛ برای استفاده از طرح جدید دو ستونی، بازنشانی چیدمان را انتخاب کنید.
- چاپ فیزیکی از گرادیانت و تم رابط جداست. ذخیرهٔ تنظیمات همچنان مستقل برای هر کاربر است.



## تغییرات نسخهٔ ۴.۵۸
نسخهٔ ۴.۵۸ — گرادیانت روشن/تیره، ۱۱ پالت تازه و اصلاح اعشار استودیو

- ۱۱ پالت Blooming romance، Desert dusk، Lavender fields، Country garden، Cherry blossom، Sunny day، Bubblegum pop، Electric kiwi، Alchemical reaction، Electropop و Neon noir اضافه شد؛ شش پالت قبلی حفظ شدند. منبع رنگ‌ها و تعدیل خوانایی در PALETTE_SOURCES.md ثبت شده است.
- گرادیانت‌های چندرنگ با توقف‌های روشن و تیره روی همهٔ صفحات مشترک و مستقل اعمال می‌شوند؛ متن محتوایی روی سطح خوانا قرار دارد. حالت روز و شب، هدر و سایدبار هماهنگ‌اند؛ چاپ فیزیکی گرادیانت نمی‌گیرد. منابع جدید برای اجرا هیچ وابستگی اینترنتی ندارند.
- ورودی‌های مختصات، ابعاد، حاشیه، قلم و مقیاس در استودیوها step=0.01 دارند. تعداد ردیف و ستون صحیح باقی است. مدل جاوااسکریپت قبل از نمایش/ذخیره به دو رقم اعشار گرد می‌شود؛ گردکردن یک‌رقمی حاشیه و قلم نامه حذف شد.
- اصلاح شامل درخواست هزینه، رسید، رانندگان، حضور دانش‌آموزان و معلمان، پشت پرونده، اطلاعات دانش‌آموز، کارت دیواری، راهنمای فیلترها، آمار، گواهی و نامه است.
- آزمون واقعی Chromium در tests/browser_studio_decimal_check.py: جابه‌جایی واقعی، اعتبار ورودی‌ها، ذخیره و بازخوانی دو رقم اعشار در ۱۲ استودیو؛ ۱۷ پالت در سه صفحه و حالت روز/شب؛ عدم اعمال گرادیانت در رسانهٔ چاپ.
- اجرای آزمون اختیاری مرورگر: pip install playwright سپس python -m playwright install --with-deps chromium و python tests/browser_studio_decimal_check.py. آزمون از دیتابیس و سرور موقت استفاده می‌کند.



## تغییرات نسخهٔ ۴.۵۹

نسخهٔ ۴.۵۹ — حافظه و دقت دستیار (بخش‌های ۲ و ۳ بررسی)
- موتور مشترک chat/stream، حفظ دادهٔ واقعی ابزار و رویداد زندهٔ مراحل.
- POST همراه CSRF؛ گفتگوهای ذخیره‌شدهٔ per-user، انتخاب، تغییر نام و حذف.
- نرمال‌سازی فارسی، تاریخ نسبی شمسی و سال تحصیلی با ساعت تهران.
- صفحه‌بندی و اعلام تعداد/پوشش؛ محدودیت اجرا و خواندن SQL.
- result_id، گزارش مستقیم از داده، محاسبات Decimal و خروجی Excel.
- حافظهٔ کاری ساختاریافته و ارزیابی فارسی با دادهٔ ساختگی.
- ۶۷ تست قبلی + ۲۱ تست جدید + ۱۵ سناریوی مرجع و تست واقعی Chromium موفق.
- بازطراحی جامع مجوزها، رضایت ارسال خارجی و تأیید تغییر SQL موکول است.
- پخش زنده مربوط به رویداد ابزار است، نه توکن‌به‌توکن مدل؛ مدل زنده ارزیابی نشده.
- راهنمای کامل، حدود نگهداری و دستور ارزیابی: AI_AGENT_459_FA.md.


## تغییرات نسخهٔ ۴.۶۰

نسخهٔ ۴.۶۰ — مرکز اتصال هوش مصنوعی و چرخهٔ اسناد
- نمایش مدل‌های نصب‌شدهٔ Ollama از API واقعی tags، همراه حجم و تفکیک وضعیت اتصال.
- پروفایل‌های مستقل، کلید مقید به مقصد، تست متن/JSON/ابزار، مدل مستقل اسناد و دستیار.
- سیاست ارسال خارجی و رضایت هر درخواست، placeholder به‌جای دادهٔ واقعی، پایش مصرف و تاریخچهٔ تنظیمات.
- نامهٔ گروهی، سابقهٔ مالی منتخب، سال تحصیلی صحیح، فیلتر گروهی و ذخیرهٔ فرم.
- پیش‌نویس و بایگانی per-user، ویرایش/اصلاح AI، نسخه‌بندی، شمارهٔ یکتا و ابطال.
- کنترل سرریز و چیدمان جاری، Word قابل‌ویرایش و PDF فارسی مستقل با قالب متنی.
- انتقال نتیجهٔ جستجوی دستیار به انتخاب دانش‌آموزان در بخش اسناد.
- ۶۷ + ۲۱ + ۲۰ تست واحد AI و تست‌های قبلی موفق؛ Chromium واقعی و PDF بازبینی شدند.
- مدل واقعی سیستم کاربر/سرویس ابری آزمایش نشده؛ آزمون اتصال از داخل تنظیمات اجرا شود.
- وابستگی‌های جدید: requirements.txt را نصب کنید. راهنمای کامل و حدود قابلیت‌ها: AI_DOCUMENTS_460_FA.md.


## نسخهٔ ۴.۶۲
نسخهٔ ۴.۶۲ — استودیوی طراحی نامه و جدول HTML/CSS
- استودیوی مشترک در اسناد و دستیار، مدل طراح قالب، درج محلی متن/سلول‌ها، پیش‌نمایش و ذخیرهٔ خودکار پیش‌نویس.
- ابزار design_letter برای نگارش و طراحی نامه در گفتگو؛ طراحی گزارش مبتنی بر result_id با حفظ ردیف‌های واقعی و منبع.
- خروجی PDF گرافیکی با Chromium، Word با جدول واقعی و RTL، Excel با سلول‌های امن و صفرهای ابتدایی حفظ‌شده، چاپ مرورگر.
- لینک بایگانی از کارت گزارش، بازکردن سند با شناسه، ویرایش HTML و CSS درون‌خطی، نسخه‌بندی قبلی حفظ شده.
- PDF چندصفحه‌ای با تکرار سربرگ جدول و وضعیت/شماره در پابرگ؛ آزمون ۲۰۰ ردیف و ۱۱ صفحه موفق.
- ۶۹ تست دستیار + ۲۱ حافظه + ۲۰ کنترل اتصال/بایگانی + ۱۲ طراحی موفق؛ آزمون‌های مرورگر هر دو استودیو و رگرسیون موفق.
- نصب وابستگی‌ها و مرورگر لازم: python -m pip install -r requirements.txt سپس python -m playwright install chromium.
- راهنمای کامل و تفاوت خروجی‌ها: AI_DESIGN_462_FA.md. مدل واقعی محلی/ابری در این محیط آزمایش نشده است.
