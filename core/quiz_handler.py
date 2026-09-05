import time
import random
from typing import Dict, Any, Optional, List


def check_and_handle_quiz(page: Any, mode: str = "auto") -> Optional[Dict[str, Any]]:
    """
    Check if a YuJa in-video quiz overlay is currently active.
    If active and mode is 'auto', automatically answers with human-like timing and resumes playback.
    """
    try:
        quiz_state = page.evaluate('''() => {
            // Check for YuJa quiz modal dialogs or overlay containers
            const quizContainer = document.querySelector('.quiz-overlay, .quiz-card, #quizContainer, .in-video-quiz, [id*="quiz"], [class*="quiz"]');
            if (!quizContainer) return null;

            // Check if visible
            const rect = quizContainer.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return null;

            // Find question text
            const qEl = quizContainer.querySelector('.question-text, .quiz-question, h3, h4, p');
            const questionText = qEl ? qEl.innerText.trim() : "Check for understanding question";

            // Find options
            const optionEls = Array.from(quizContainer.querySelectorAll('input[type="radio"], input[type="checkbox"], .quiz-option, .answer-choice, [role="radio"]'));
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

        # Handle quiz in auto mode with human-like pacing
        if mode in ("auto", "heuristic"):
            # 1. Human reading pause: wait 3.2 to 5.5 seconds simulating reading the question
            reading_delay = random.uniform(3.2, 5.5)
            time.sleep(reading_delay)

            # 2. Select option with mouse hover simulation
            page.evaluate('''() => {
                const quizContainer = document.querySelector('.quiz-overlay, .quiz-card, #quizContainer, .in-video-quiz, [id*="quiz"], [class*="quiz"]');
                if (!quizContainer) return;

                const options = Array.from(quizContainer.querySelectorAll('input[type="radio"], input[type="checkbox"], .quiz-option, .answer-choice, [role="radio"]'));
                if (options.length > 0) {
                    const chosen = options[0];
                    chosen.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    chosen.focus();
                    chosen.click();
                    chosen.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }''')

            # 3. Human decision delay before hitting submit: wait 1.4 to 2.8 seconds
            time.sleep(random.uniform(1.4, 2.8))

            # 4. Click Save / Submit / Continue button
            handled = page.evaluate('''() => {
                const quizContainer = document.querySelector('.quiz-overlay, .quiz-card, #quizContainer, .in-video-quiz, [id*="quiz"], [class*="quiz"]');
                if (!quizContainer) return false;

                const saveBtn = Array.from(quizContainer.querySelectorAll('button, div[role="button"], input[type="submit"]')).find(b => {
                    const t = (b.innerText || b.value || '').toLowerCase();
                    return t.includes('save') || t.includes('submit') || t.includes('continue') || t.includes('next') || t.includes('confirm');
                });
                if (saveBtn) {
                    saveBtn.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    saveBtn.focus();
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
