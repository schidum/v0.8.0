from celery import shared_task
from fpdf import FPDF
from app.database import AsyncSessionLocal
from app.repositories import TaskRepository
from app.tasks.async_runner import run_async_task
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def generate_completed_tasks_report(self, request_dict: dict):
    """
    Generate a PDF report of completed tasks.
    Uses safe async execution to prevent event loop conflicts.
    """
    try:
        async def _run():
            async with AsyncSessionLocal() as db:
                repo = TaskRepository(db)
                tasks = await repo.list_all()
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.cell(200, 10, "Отчёт по выполненным заданиям", ln=1)
                for t in tasks:
                    if t.status == "completed":
                        pdf.cell(200, 8, f"#{t.id} {t.title} — {t.result_comment or '—'}", ln=1)
                filename = f"report_{self.request.id}.pdf"
                pdf.output(f"static/reports/{filename}")
                logger.info(f"Report generated: {filename}")
                return {"report_url": f"/static/reports/{filename}"}
        
        return run_async_task(_run())
    except Exception as exc:
        logger.error(f"Error generating report: {exc}", exc_info=True)
        raise