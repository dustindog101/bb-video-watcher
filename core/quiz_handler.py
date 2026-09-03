"""
In-Video Quiz and Check-for-Understanding Interceptor for YuJa Player.
Detects interactive quiz overlay modals, extracts question schemas, and handles responses.
"""

from typing import Dict, Any, Optional, List


def check_and_handle_quiz(page: Any, mode: str = "auto") -> Optional[Dict[str, Any]]:
    """
    Check if a YuJa in-video quiz overlay is currently active.
    If active and mode is 'auto', automatically answers and resumes playback.
    """
    try:
        quiz_state = page.evaluate('''() => {
            // Check for YuJa quiz modal dialogs or overlay containers
            const quizContainer = document.querySelector('.quiz-overlay, .quiz-card, #quizContainer, .in-video-quiz, [id*="quiz"]');
            if (!quizContainer) return null;

            // Check if visible
            const rect = quizContainer.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return null;

            // Find question text
            const qEl = quizContainer.querySelector('.question-text, .quiz-question, h3, h4');
            const questionText = qEl ? qEl.innerText.trim() : "Check for understanding question";

            // Find options
            const optionEls = Array.from(quizContainer.querySelectorAll('input[type="radio"], input[type="checkbox"], .quiz-option, .answer-choice'));
            const options = optionEls.map(o => {
                const label = o.closest('label') || o.nextElementSibling;
                return label ? label.innerText.trim() : (o.value || "Option");
            });

            return {
                found: true,
                question: questionText,
                options: options,
                optionCount: optionEls.length
            };
        }''')

        if not quiz_state or not quiz_state.get("found"):
            return None

        # Handle quiz in auto mode
        if mode in ("auto", "heuristic"):
            handled = page.evaluate('''() => {
                const quizContainer = document.querySelector('.quiz-overlay, .quiz-card, #quizContainer, .in-video-quiz, [id*="quiz"]');
                if (!quizContainer) return false;

                // Select the first radio or checkbox
                const firstOption = quizContainer.querySelector('input[type="radio"], input[type="checkbox"], .quiz-option');
                if (firstOption) {
                    firstOption.click();
                }

                // Click Save / Submit / Continue button
                const saveBtn = Array.from(quizContainer.querySelectorAll('button, div[role="button"]')).find(b => {
                    const t = (b.innerText || '').toLowerCase();
                    return t.includes('save') || t.includes('submit') || t.includes('continue') || t.includes('next');
                });
                if (saveBtn) {
                    saveBtn.click();
                    return true;
                }
                return false;
            }''')
            quiz_state["handled"] = handled
            return quiz_state

        return quiz_state

    except Exception:
        return None
