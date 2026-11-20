export interface HotspotCredentials {
  username: string;
  password: string;
}

export function submitHotspotLogin(
  loginUrl: string,
  destination: string,
  credentials: HotspotCredentials,
) {
  const url = new URL(loginUrl, window.location.href);
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('Unsupported hotspot login URL protocol.');
  }
  if (destination && !url.searchParams.has('dst')) {
    url.searchParams.set('dst', destination);
  }

  const form = document.createElement('form');
  form.method = 'post';
  form.action = url.toString();
  form.style.display = 'none';
  for (const [name, value] of Object.entries(credentials)) {
    const field = document.createElement('input');
    field.type = 'hidden';
    field.name = name;
    field.value = value;
    form.appendChild(field);
  }
  document.body.appendChild(form);
  form.submit();
}
