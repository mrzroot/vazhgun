"""Synthetic thesis chapter used by --demo and the tests (invented text; not from any real thesis)."""
from __future__ import annotations

from .docxbuild import Doc

RLM, LRM = "\u200f", "\u200e"


def chapter(path: str, flawed: bool = True, marks: str = "none") -> str:
    """marks: 'none' (nothing marked) or 'reading' (every number chain carries an RLM after the separator)."""
    def N(a: str, b: str) -> str:
        return f"{a}-{RLM}{b}" if marks == "reading" else f"{a}-{b}"

    sep = "-" + (RLM if marks == "reading" else "")
    d = Doc()
    d.add_footer()
    d.heading("فصل دوم: مبانی نظری و پیشینه پژوهش", 1)
    d.p("در این فصل مفاهیم پایه‌ی مدل‌سازی شبکه‌های توزیع آب شهری مرور می‌شود و نتایج مطالعات پیشین با نرم‌افزار EPANET مقایسه می‌گردد.")
    d.p(f"مطابق شکل {N('۲', '۱')} شبکه از ۱۴ گره و ۱۸ لوله تشکیل شده است. داده‌ها در بازه‌ی سال‌های {N('۱۳۹۸', '۱۴۰۱')} گردآوری شد (Smith, 2020).")
    d.caption_seq("شکل", 2, 1, "طرح کلی شبکه‌ی آزمایشی", sep=sep)
    d.p(f"جزئیات روش در صفحات {N('۱۲', '۱۵')} پایان‌نامه آمده است و نتیجه‌ی آن در شکل {N('۲', '۲')} دیده می‌شود.")
    d.caption_seq("شکل", 2, 2, "تغییرات فشار در طول شبانه‌روز", sep=sep)
    minus = "-" if flawed else LRM + "-"
    d.p(f"دمای محیط در شب‌های زمستان تا {minus}۵ درجه‌ی سانتی‌گراد کاهش یافت و ضریب اصطکاک از ۰٫۰۲ به ۰٫۰۳ رسید.")
    date = "۱۴۰۳/۰۹/۰۴" if marks != "reading" else f"۱۴۰۳/{RLM}۰۹/{RLM}۰۴"
    d.p(f"نمونه‌ها در تاریخ {date} برداشت شدند.")
    d.p("افت فشار از رابطه‌ی دارسی–وایسباخ به دست می‌آید:")
    d.p(f"({N('۲', '۴')})", jc="center")
    d.p(f"همان‌طور که در Fig. {N('۲', '۳')} آمده است، گره‌های میانی بیشترین افت را دارند.")
    d.p(f"جدول {N('۲', '۱')} ویژگی‌های لوله‌ها را نشان می‌دهد.")
    d.table([["قطر (میلی‌متر)", "جنس", "طول (متر)"], ["۲۰۰", "چدن", "۴۵۰"], ["۳۰۰", "پلی‌اتیلن", "۸۲۰"]],
            bidi_visual=not flawed)
    d.caption_seq("جدول", 2, 1, "ویژگی‌های لوله‌ها", seq="Table", sep=sep)
    if flawed:
        d.p("این بند از فایل PDF کپی شده و جهت پاراگراف آن چپ‌به‌راست است (ذخیره‌شده توسط ابزار دیگر).", bidi=False, jc="left")
        d.p(f"نتیجه در جدول {N('۲', '۲')} بررسی شد.\u202b")      # stray RLE pasted from a PDF
    else:
        d.p(f"نتیجه در جدول {N('۲', '۲')} بررسی شد.")
    d.p("The proposed model follows Rossman (2000), see Fig. 2-3.", bidi=False, jc="both")
    return d.save(path)
