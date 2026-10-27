(function () {
  'use strict';

  const conceptPage = document.querySelector('.concept-page');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let firstVisit = false;

  try {
    firstVisit = !reducedMotion.matches && sessionStorage.getItem('reform-life-concept-intro') !== 'seen';
    if (firstVisit) sessionStorage.setItem('reform-life-concept-intro', 'seen');
  } catch (_error) {
    firstVisit = !reducedMotion.matches;
  }

  conceptPage?.classList.toggle('motion-intro', firstVisit);

  const taskRows = Array.from(document.querySelectorAll('[data-task-done]'));
  const progressRing = document.getElementById('progressRing');
  const progressValue = document.getElementById('progressValue');

  function updateProgress() {
    if (!progressRing || !progressValue) return;
    const completed = taskRows.filter((row) => row.classList.contains('complete')).length;
    const total = taskRows.length;
    const percent = total ? Math.round((completed / total) * 100) : 0;
    progressValue.textContent = `${percent}%`;
    progressValue.classList.remove('is-updating');
    void progressValue.offsetWidth;
    progressValue.classList.add('is-updating');
    const inactive = 'rgba(255,255,255,.08)';
    progressRing.style.borderTopColor = percent >= 25 ? 'var(--concept-orange)' : inactive;
    progressRing.style.borderRightColor = percent >= 50 ? 'var(--concept-orange)' : inactive;
    progressRing.style.borderBottomColor = percent >= 75 ? 'var(--concept-orange)' : inactive;
    progressRing.style.borderLeftColor = percent >= 100 ? 'var(--concept-orange)' : inactive;
  }

  taskRows.forEach((row) => {
    row.addEventListener('click', () => {
      row.classList.toggle('complete');
      const isDone = row.classList.contains('complete');
      row.dataset.taskDone = String(isDone);
      row.querySelector('.checkmark').textContent = isDone ? '✓' : '';
      const tag = row.querySelector('.task-tag');
      if (!tag) {
        updateProgress();
        return;
      }
      if (isDone && tag.classList.contains('active')) {
        tag.classList.remove('active');
        tag.textContent = 'готово';
      } else if (!isDone) {
        tag.classList.add('active');
        tag.textContent = 'фокус';
      }
      updateProgress();
    });
  });

  document.querySelectorAll('.habit-check').forEach((button) => {
    button.addEventListener('click', () => {
      button.classList.toggle('checked');
      button.textContent = button.classList.contains('checked') ? '✓' : '';
      button.setAttribute('aria-pressed', String(button.classList.contains('checked')));
    });
    button.setAttribute('aria-pressed', String(button.classList.contains('checked')));
  });

  document.querySelectorAll('.day-tabs button').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.day-tabs button').forEach((item) => item.classList.remove('selected'));
      button.classList.add('selected');
    });
  });

  document.querySelectorAll('.mood-options button').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.mood-options button').forEach((item) => item.classList.remove('selected'));
      button.classList.add('selected');
    });
  });

  document.querySelectorAll('.concept-nav-link').forEach((link) => {
    link.addEventListener('click', () => {
      document.querySelectorAll('.concept-nav-link').forEach((item) => item.classList.remove('active'));
      link.classList.add('active');
    });
  });

  const observedSections = Array.from(document.querySelectorAll('.concept-main > section[id]'));
  const navLinks = Array.from(document.querySelectorAll('.concept-nav-link'));
  if ('IntersectionObserver' in window && observedSections.length && navLinks.length) {
    const sectionObserver = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      navLinks.forEach((link) => link.classList.toggle('active', link.getAttribute('href') === `#${visible.target.id}`));
    }, { rootMargin: '-22% 0px -62% 0px', threshold: [0, .25, .6] });
    observedSections.forEach((section) => sectionObserver.observe(section));
  }

  updateProgress();
}());
