// Keep desktop navigation visible and collapse it on small screens.
const toggle = document.querySelector('.nav-toggle');
const sidebar = document.querySelector('.sidenav');
if (toggle && sidebar) {
  document.documentElement.classList.add('has-navigation-js');
  const closeNavigation = () => {
    sidebar.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '展开导航';
  };
  toggle.addEventListener('click', () => {
    const open = sidebar.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? '收起导航' : '展开导航';
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && sidebar.classList.contains('is-open')) {
      closeNavigation();
      toggle.focus();
    }
  });
  window.matchMedia('(min-width: 901px)').addEventListener('change', closeNavigation);
}
