(function () {
  'use strict';

  const taskRows = Array.from(document.querySelectorAll('[data-task-done]'));
  const progressRing = document.getElementById('progressRing');
  const progressValue = document.getElementById('progressValue');

  function updateProgress() {
    const completed = taskRows.filter((row) => row.classList.contains('complete')).length;
    const total = taskRows.length;
    const percent = total ? Math.round((completed / total) * 100) : 0;
    progressValue.textContent = `${percent}%`;
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
    });
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
}());
