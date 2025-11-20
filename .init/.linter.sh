#!/bin/bash
cd /home/kavia/workspace/code-generation/career-pathway-navigator-278563-278572/career_navigator_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

