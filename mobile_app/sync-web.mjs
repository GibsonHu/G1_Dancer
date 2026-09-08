import { cp, mkdir } from 'node:fs/promises';
await mkdir(new URL('./www', import.meta.url), {recursive:true});
await cp(new URL('../g1_dancer/web/', import.meta.url), new URL('./www/', import.meta.url), {recursive:true});
await cp(new URL('../g1_dancer/assets/', import.meta.url), new URL('./www/assets/', import.meta.url), {recursive:true});
console.log('Shared desktop and mobile interface copied.');
