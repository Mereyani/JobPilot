"""Minimal i18n: a flat string table plus a `t(key, **kwargs)` lookup.

No translation framework - just a dict, because the dashboard is a handful
of templates and a real i18n library would be more machinery than the
problem needs.
"""

from collections.abc import Callable

DEFAULT_LANG = "en"
LANGUAGES = {"en": "English", "ar": "العربية"}

_STRINGS: dict[str, dict[str, str]] = {
    "nav.dashboard": {"en": "Dashboard", "ar": "لوحة التحكم"},
    "nav.settings": {"en": "Settings", "ar": "الإعدادات"},
    "nav.github": {"en": "GitHub ↗", "ar": "GitHub ↗"},
    "dashboard.title": {"en": "Dashboard", "ar": "لوحة التحكم"},
    "dashboard.subtitle": {
        "en": "Searching {countries} for “{roles}”.",
        "ar": "يبحث في {countries} عن وظائف “{roles}”.",
    },
    "action.run_search": {"en": "Run search", "ar": "تشغيل البحث"},
    "action.run_matching": {"en": "Run matching", "ar": "تشغيل المطابقة"},
    "action.send_applications": {"en": "Send applications", "ar": "إرسال التقديمات"},
    "action.check_email": {"en": "Check email", "ar": "فحص البريد"},
    "stat.jobs_found": {"en": "Jobs found", "ar": "وظائف تم العثور عليها"},
    "stat.above_threshold": {"en": "Above match threshold ({threshold})", "ar": "فوق نسبة التطابق ({threshold})"},
    "stat.applications_sent": {"en": "Applications sent", "ar": "تقديمات مُرسلة"},
    "stat.interview_replies": {"en": "Interview replies", "ar": "ردود مقابلات"},
    "section.jobs": {"en": "Jobs", "ar": "الوظائف"},
    "section.applications": {"en": "Applications", "ar": "التقديمات"},
    "section.recent_emails": {"en": "Recent emails", "ar": "أحدث الرسائل"},
    "col.score": {"en": "Score", "ar": "النسبة"},
    "col.title": {"en": "Title", "ar": "المسمى الوظيفي"},
    "col.company": {"en": "Company", "ar": "الشركة"},
    "col.country": {"en": "Country", "ar": "الدولة"},
    "col.source": {"en": "Source", "ar": "المصدر"},
    "col.job": {"en": "Job", "ar": "الوظيفة"},
    "col.status": {"en": "Status", "ar": "الحالة"},
    "col.reason": {"en": "Reason", "ar": "السبب"},
    "reason.no_contact_email": {
        "en": "No contact email found on listing — apply manually",
        "ar": "لم يُعثر على إيميل تواصل في الإعلان — التقديم يدوياً",
    },
    "col.applied_at": {"en": "Applied at", "ar": "تاريخ التقديم"},
    "col.direction": {"en": "Direction", "ar": "الاتجاه"},
    "col.subject": {"en": "Subject", "ar": "الموضوع"},
    "col.category": {"en": "Category", "ar": "التصنيف"},
    "col.from_to": {"en": "From/To", "ar": "من/إلى"},
    "empty.jobs": {"en": "No jobs yet — click “Run search”.", "ar": "لا توجد وظائف بعد — اضغط “تشغيل البحث”."},
    "empty.applications": {"en": "No applications sent yet.", "ar": "لم يتم إرسال أي تقديم بعد."},
    "empty.emails": {"en": "No emails yet.", "ar": "لا توجد رسائل بعد."},
    "link.open": {"en": "open ↗", "ar": "فتح ↗"},
    "col.select": {"en": "Select", "ar": "اختيار"},
    "action.apply_selected": {"en": "Apply to selected", "ar": "التقديم على المحدد"},
    "status.pending": {"en": "Pending", "ar": "قيد المعالجة"},
    "status.applied": {"en": "Sent", "ar": "تم الإرسال"},
    "status.failed": {"en": "Failed", "ar": "فشل"},
    "status.interview": {"en": "Interview", "ar": "مقابلة"},
    "status.rejected": {"en": "Rejected", "ar": "مرفوض"},
    "status.replied": {"en": "Replied", "ar": "تم الرد"},
    "settings.title": {"en": "Settings", "ar": "الإعدادات"},
    "settings.subtitle": {
        "en": "Everything here is stored locally in your own database — nothing is shared or committed.",
        "ar": "كل ما هنا يُخزَّن محلياً في قاعدة بياناتك الخاصة — لا شيء يُشارَك أو يُرفع إلى المستودع.",
    },
    "settings.saved": {"en": "Saved.", "ar": "تم الحفظ."},
    "settings.ai_provider": {"en": "AI provider", "ar": "مزوّد الذكاء الاصطناعي"},
    "settings.ai_provider_hint": {
        "en": "Pick the model that scores job matches and writes cover letters / replies.",
        "ar": "اختر النموذج الذي يقيّم مطابقة الوظائف ويكتب رسائل التقديم والردود.",
    },
    "provider.anthropic": {"en": "Anthropic (Claude)", "ar": "Anthropic (Claude)"},
    "provider.google": {"en": "Google (Gemini)", "ar": "Google (Gemini)"},
    "provider.ollama": {"en": "Ollama (local, no key needed)", "ar": "Ollama (محلي، بدون مفتاح)"},
    "field.anthropic_key": {"en": "Anthropic API key", "ar": "مفتاح Anthropic"},
    "field.anthropic_model": {"en": "Anthropic model", "ar": "نموذج Anthropic"},
    "field.google_key": {"en": "Google API key", "ar": "مفتاح Google"},
    "field.google_model": {"en": "Google model", "ar": "نموذج Google"},
    "field.ollama_url": {"en": "Ollama base URL", "ar": "رابط خادم Ollama"},
    "field.ollama_model": {"en": "Ollama model (must already be pulled)", "ar": "نموذج Ollama (يجب تحميله مسبقاً)"},
    "settings.email": {"en": "Email", "ar": "البريد الإلكتروني"},
    "settings.email_hint": {
        "en": "Used to send applications/replies (SMTP) and read the inbox for responses (IMAP). For Gmail, use an app password, not your normal password.",
        "ar": "يُستخدم لإرسال التقديمات/الردود (SMTP) وقراءة صندوق الوارد (IMAP). لحسابات Gmail، استخدم app password وليس كلمة المرور العادية.",
    },
    "field.email_address": {"en": "Email address", "ar": "البريد الإلكتروني"},
    "field.app_password": {"en": "App password", "ar": "كلمة مرور التطبيق"},
    "settings.quick_fill": {"en": "Quick fill:", "ar": "تعبئة سريعة:"},
    "field.imap_host": {"en": "IMAP host", "ar": "خادم IMAP"},
    "field.imap_port": {"en": "IMAP port", "ar": "منفذ IMAP"},
    "field.smtp_host": {"en": "SMTP host", "ar": "خادم SMTP"},
    "field.smtp_port": {"en": "SMTP port", "ar": "منفذ SMTP"},
    "field.auto_send": {
        "en": "Auto-send replies (uncheck to only draft them for now)",
        "ar": "إرسال الردود تلقائياً (ألغِ التحديد لكتابة مسودة فقط حالياً)",
    },
    "settings.job_search": {"en": "Job search", "ar": "البحث عن وظائف"},
    "field.countries": {"en": "Countries (comma-separated)", "ar": "الدول (مفصولة بفواصل)"},
    "field.roles": {"en": "Roles (comma-separated)", "ar": "المسميات الوظيفية (مفصولة بفواصل)"},
    "field.resume_path": {"en": "Resume path", "ar": "مسار السيرة الذاتية"},
    "field.match_threshold": {"en": "Match threshold (0-100)", "ar": "الحد الأدنى للتطابق (0-100)"},
    "field.auto_apply_threshold": {"en": "Auto-apply threshold (0-100)", "ar": "حد التقديم التلقائي (0-100)"},
    "settings.threshold_hint": {
        "en": "Jobs scoring at/above the auto-apply threshold are sent automatically. Jobs between the two thresholds show up on the dashboard for you to pick from instead.",
        "ar": "الوظائف التي تصل نسبتها لحد التقديم التلقائي أو أعلى تُرسل تلقائياً. الوظائف بين الحدّين تظهر في اللوحة لتختار منها بنفسك.",
    },
    "settings.pacing": {"en": "Application pacing", "ar": "وتيرة إرسال التقديمات"},
    "settings.pacing_hint": {
        "en": "Applications are sent this many at a time, then JobPilot waits before the next batch.",
        "ar": "يتم إرسال هذا العدد من التقديمات دفعة واحدة، ثم ينتظر JobPilot قبل الدفعة التالية.",
    },
    "field.batch_size": {"en": "Batch size", "ar": "حجم الدفعة"},
    "field.batch_interval": {"en": "Minutes between batches", "ar": "الدقائق بين الدفعات"},
    "settings.auto_run": {"en": "Automatic runs", "ar": "التشغيل التلقائي"},
    "settings.auto_run_hint": {
        "en": "When enabled, JobPilot runs the whole pipeline (search → match → apply → check email) by itself on this interval - including sending real applications, unattended.",
        "ar": "عند التفعيل، سيشغّل JobPilot خط الأنابيب كاملاً (بحث ← مطابقة ← تقديم ← فحص بريد) تلقائياً على هذا الفاصل الزمني — بما في ذلك إرسال تقديمات حقيقية دون إشراف.",
    },
    "field.auto_run_enabled": {"en": "Run automatically", "ar": "تشغيل تلقائي"},
    "field.auto_run_interval": {"en": "Every how many hours", "ar": "كل كم ساعة"},
    "action.save_settings": {"en": "Save settings", "ar": "حفظ الإعدادات"},
    "placeholder.saved_secret": {
        "en": "•••• saved — leave blank to keep",
        "ar": "•••• محفوظ — اتركه فارغاً للإبقاء عليه",
    },
}


def translator(lang: str) -> Callable[..., str]:
    def t(key: str, **kwargs) -> str:
        entry = _STRINGS.get(key)
        if entry is None:
            return key
        text = entry.get(lang) or entry.get(DEFAULT_LANG, key)
        return text.format(**kwargs) if kwargs else text

    return t
