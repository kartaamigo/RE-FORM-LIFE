document.addEventListener('DOMContentLoaded', () => {
  const library = document.getElementById('assistantCommandLibrary');
  if (!library) return;
  const form = document.getElementById('assistantCustomCommandForm');
  const status = document.getElementById('assistantCommandsStatus');
  const field = suffix => document.getElementById(`assistantCustomCommand${suffix}`);
  let commands = [];
  let catalog = [];
  const report = message => { status.textContent = message; };

  const useExample = text => {
    const input = document.getElementById('assistantCommand');
    input.value = text;
    input.dispatchEvent(new Event('input'));
    input.focus();
  };
  const reset = () => { form.reset(); field('Id').value = ''; };
  const edit = item => {
    field('Id').value = item.id;
    for (const key of ['name', 'phrase', 'template', 'mode']) field(key[0].toUpperCase() + key.slice(1)).value = item[key];
    field('Enabled').checked = item.enabled;
    field('Phrase').focus();
  };
  const button = (label, handler) => {
    const item = document.createElement('button');
    item.type = 'button'; item.className = 'button ghost small';
    item.textContent = label;
    item.addEventListener('click', async () => {
      item.disabled = true;
      try { await handler(); } catch (error) { report(error.message); }
      finally { item.disabled = false; }
    });
    return item;
  };
  const render = () => {
    const basics = document.getElementById('assistantCommandCatalog');
    basics.replaceChildren();
    for (const example of catalog) {
      const row = document.createElement('div'); row.className = 'assistant-command-entry';
      const label = document.createElement('p');
      label.textContent = `${example.category} · ${example.description}${example.requires_ai ? ' · ИИ' : ''}`;
      row.append(label, button(example.text, () => useExample(example.text)), button('Сделать своей', () => {
        reset(); field('Name').value = example.description; field('Template').value = example.text;
        field('Mode').value = example.requires_ai ? 'prompt' : 'command'; field('Phrase').focus();
      }));
      basics.append(row);
    }
    const custom = document.getElementById('assistantCustomCommands');
    custom.replaceChildren();
    if (!commands.length) { const empty = document.createElement('p'); empty.textContent = 'Своих команд пока нет. Создай первую ниже.'; custom.append(empty); }
    for (const item of commands) {
      const row = document.createElement('div'); row.className = 'assistant-command-entry';
      const label = document.createElement('p');
      label.textContent = `${item.name}: «${item.phrase}» → ${item.template}${item.enabled ? '' : ' · выключена'}${item.mode === 'prompt' ? ' · ИИ' : ''}`;
      row.append(label, button('Редактировать', () => edit(item)), button(item.enabled ? 'Выключить' : 'Включить', async () => {
        await api(`/api/assistant/commands/${item.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !item.enabled }) });
        await load();
      }), button('Удалить', async () => {
        if (!window.confirm(`Удалить свою команду «${item.name}»?`)) return;
        await api(`/api/assistant/commands/${item.id}`, { method: 'DELETE' });
        if (Number(field('Id').value) === item.id) reset();
        await load(); report('Команда удалена.');
      }));
      custom.append(row);
    }
  };
  const load = async () => {
    const result = await api('/api/assistant/commands');
    commands = result.commands; catalog = result.catalog; render();
  };
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = form.querySelector('[type="submit"]'); submit.disabled = true;
    try {
      const id = field('Id').value;
      const data = { name: field('Name').value, phrase: field('Phrase').value, template: field('Template').value, mode: field('Mode').value, enabled: field('Enabled').checked };
      await api(id ? `/api/assistant/commands/${id}` : '/api/assistant/commands', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(data) });
      reset(); await load(); report('Своя команда сохранена. Можно написать или произнести её фразу.');
    } catch (error) { report(error.message); } finally { submit.disabled = false; }
  });
  document.getElementById('assistantCustomCommandReset').addEventListener('click', reset);
  document.getElementById('assistantComposerHelp').addEventListener('click', () => { library.open = true; library.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); });
  const fileInput = document.getElementById('assistantCommandsFile');
  document.getElementById('assistantImportCommands').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async () => {
    try {
      const file = fileInput.files[0]; if (!file) return;
      if (file.size > 128000) throw new Error('Файл больше 128 КБ.');
      const data = JSON.parse(await file.text());
      const result = await api('/api/assistant/commands/import', { method: 'POST', body: JSON.stringify(data) });
      await load(); report(`Импортировано команд: ${result.imported}. Проверь их перед использованием.`);
    } catch (error) { report(error.message); } finally { fileInput.value = ''; }
  });
  load().then(() => report('Основные команды доступны. Можно добавить свои.')).catch(error => report(error.message));
});
