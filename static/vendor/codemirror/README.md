# CodeMirror 6

Éditeur des notes (#89), chargé par `note_taking/static/note_taking/editor.js` sur les pages de création et de modification d'une note. Rien n'est chargé depuis Internet : une import map (`{% codemirror_importmap %}`) renvoie chaque module vers ce dossier.

Fichier généré par `python manage.py vendor_codemirror` à partir de `packages.json` ; ne pas le modifier à la main.

- Source : archives npm officielles (`https://registry.npmjs.org/<paquet>/-/…tgz`), dont l'empreinte (`dist.integrity` du registre) est vérifiée avant l'extraction.
- Fichiers : `index.js` (le fichier d'entrée ES indiqué) et `LICENSE` de chaque paquet, dans un dossier au nom du paquet (`@codemirror/state` → `codemirror-state/`).
- Versions : la plus récente publiée depuis au moins deux semaines au moment du choix.
- Ajouter un module : une ligne dans `packages.json` (nom, version, fichier d'entrée), puis `python manage.py vendor_codemirror`. Un test vérifie que tous les modules importés par ces fichiers sont dans la liste.

| Paquet | Version | Fichier d'entrée | SHA-256 de `index.js` | Empreinte de l'archive |
|---|---|---|---|---|
| `@codemirror/state` | 6.7.6 | `dist/index.js` | `cf4ffe7d177bf2c7c5da66c49be0811cc79a29e12cb658238876bbdcef12939c` | `sha512-kAz+AncRtKuIknedxT1bq4XwXv4UowhbkHU1myPrtVb/jZtImWuV5BXzv5vK6i3kYACsdiZiQKFQQ5Mq7elW8w==` |
| `@codemirror/view` | 6.43.14 | `dist/index.js` | `73339f0c64071b55fc2d24e69ad6527a37068c2465b1fec3a50726923f3b7ea5` | `sha512-hC45YnmJNR1rz42OF57BLoQNFMV12/13drnvibDsR2quNDmldcb4WvYVV81hFQg56i9lcqQMEDqilhX2QDcGQQ==` |
| `@codemirror/commands` | 6.11.1 | `dist/index.js` | `395c41fb17d4966162e8d29106e438278123bc3a3fa1b11825debdf1523594a4` | `sha512-O/4hG3SC1YwcmQ0d2UVNDs+AsaNWd1iHVxbTeEBuqH+6bExAiPK3iS/BvpY6rZGURALv4ZD3sIgcCmRvw3ehBg==` |
| `@codemirror/language` | 6.13.1 | `dist/index.js` | `3ee82597686d97904b1c0df409661c2e6386e206b9122ac309622e225a0075ff` | `sha512-zfvU2r3TyylQLMj/te+5CnQ0rSqZi8B1oTCBbQkagcLW4Xc6imab6qN+pEJhsuNOLaJqiRyBXp9UhWA1DhVvDw==` |
| `@codemirror/search` | 6.7.2 | `dist/index.js` | `1155a69fb8d6f56c1d644e3e93222348481d6b2df78d6bebcf3293fe209f3fd7` | `sha512-gUYkYhT2+n/+VGZ+8EzE5WFkYZUZYm1VOKDudIsNqh42uRVQJ0a6Yss9sdKT3MeOYfuL1N6AZA57oza0Oyr0LA==` |
| `@codemirror/streamparser` | 6.0.0 | `dist/index.js` | `03b1109bc091c1f70e34abbd6161cd1675280a10ac5d26fffdede446076e4bb6` | `sha512-JTFPF6xrfjt0mnfGPgzcLiMwYmvIyNaoizp8BYzv8FE8KrT6GBGDZ190rtt+O7Wke3gG/MFHyiY9YGNeimof4w==` |
| `@lezer/common` | 1.5.3 | `dist/index.js` | `4f08d3cc772b63930aa424b5f75f41c244f2de98da43cd0d72e157a6cbff2dd5` | `sha512-H0iErY4e43LpXbYDyBci5W4v/RwTgGV3YzYOlJPiGZ8RY8w51kVE+xLn1tg3Z6UmSfyETvtsUK3r7YsgDQEI7Q==` |
| `@lezer/highlight` | 1.2.5 | `dist/index.js` | `8984bb2887a6354d3e5ac79bdd7e522948f1cee1dda16aac77d9473f10696d7c` | `sha512-O1GMVKgtf5YspFaRzpmqkVgMtIk2HG9uMAbH6wdAIdNh3TVzCsch/+cRi+6l2//UGDKe6NB9BW3cvuR5ezMQ0w==` |
| `@lezer/markdown` | 1.8.0 | `dist/index.js` | `5d3e761ba9d49ba81ddf0f148c02196d3ede2d4aa2b76a939e454eb88cbfb12c` | `sha512-X6w3A2NpyhdtGqTWRJB8gR4QDXBaFMbTOs780ZdZ15KKCfBXOQTKcB3Vr+W6tqJHVlealt53tLmHRvOqPTQgYA==` |
| `style-mod` | 4.1.4 | `src/style-mod.js` | `4bd6b34edda52f362553d33df7e3a10f31fbdc0c95125aabec89c4de6be80b0a` | `sha512-XXWIQt633/EpAFx8aZDOTjBzrCaGmhvEQlQo6MVPfa2OzO2cWo+4hV9h+6UkHYlXGfy+ODXKUdP7Pthmcu5ATw==` |
| `w3c-keyname` | 2.2.8 | `index.js` | `b649dec4f01c7c5eb05be4641b5b698c6938231ee50b38e17a2f0f822ca3df2e` | `sha512-dpojBhNsCNN7T82Tm7k26A6G9ML3NkhDsnw9n/eoxSRlVBB4CEtIQ/KTCLI2Fwf3ataSXRhYFkQi3SlnFwPvPQ==` |
| `crelt` | 1.0.7 | `index.js` | `924800defa2bf95a0bfd16dde589ecebbcd9e36b03635274da84968c77a3721e` | `sha512-aK6BbWfhf4U/wCcLHKPJl/xa6VkVstRaPywWtMKGwuOLc/wZTyQYuoxgvZnNsBvv7Kg3YTBQYYBCggcviQczuA==` |
| `@marijn/find-cluster-break` | 1.0.4 | `src/index.js` | `4e9e441fac9db54e09e4e3b1cb0b0393da207ebe943f2ff9efc577821fc03751` | `sha512-Wy0V7+SGUjnF9/TkiM1hKVDPj7jKXduPNboMVtHTA8dySMURWqfg/JZ9E2Sq8JgSJmkl7k7Qe9FLeMSrSraWmQ==` |
