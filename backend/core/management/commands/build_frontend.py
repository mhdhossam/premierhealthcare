# core/management/commands/build_frontend.py
from django.core.management.base import BaseCommand, CommandError
from core.staticfiles import build_frontend, NpmBuildFinder


class Command(BaseCommand):
    help = "Builds the frontend bundle and copies it into static/nexus_admin. Run this in CI/deploy before collectstatic."

    def handle(self, *args, **options):
        finder = NpmBuildFinder()
        self.stdout.write(f"Building frontend from {finder.frontend_dir} ...")
        try:
            build_frontend(finder.frontend_dir, finder.dist_dir, finder.static_dir)
        except RuntimeError as e:
            raise CommandError(str(e))
        self.stdout.write(self.style.SUCCESS(f"Frontend build output copied to {finder.static_dir}"))