"""Entry point: python -m ai_pm_agent"""

import logging

from . import rules_repo
from .telegram_bot import build_application

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("PM agent starting")
    ok, output = rules_repo.ensure_repo()
    if not ok:
        logger.error("Initial rules sync failed: %s", output)
    app = build_application()
    app.run_polling()


if __name__ == "__main__":
    main()
