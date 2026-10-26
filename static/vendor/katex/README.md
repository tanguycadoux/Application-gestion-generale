# KaTeX 0.18.11

Bibliothèque embarquée pour afficher les formules LaTeX des notes (#99), chargée par le gabarit de base des notes (`note_taking/templates/note_taking/base.html`) avec `note_taking/static/note_taking/math.js`.

- Source : archive npm officielle `https://registry.npmjs.org/katex/-/katex-0.18.11.tgz`, intégrité vérifiée contre le registre npm (`sha512-yvyz/2VMKqoho/35Hat5w37wIEdWJ5ElVMidTAlWrxr5uW4aBGsEpveTmKh18/zw08v/7lGswCPon4OhqmqrTA==`).
- Fichiers extraits :
  - `package/dist/katex.min.js` (SHA-256 `607cb26db8e23fba98ba8e1c0b764ff4c67af35106e59316ec5449a94083fa68`) ;
  - `package/dist/katex.min.css` (SHA-256 `b8511ee880e4981ac28bbc3d675a90cb9fa080e275f06d648147ed316cb421ba`) ;
  - `package/dist/fonts/*.woff2`, dans `fonts/` : la feuille cite pour chaque police un `woff2`, puis un `woff` et un `ttf` de secours, que les navigateurs actuels ne demandent pas ;
  - `package/LICENSE` (MIT).
- Version : la 0.19.1, publiée le 2026-10-23, était trop récente lors de l'ajout (2026-10-26). La 0.18.11 était la dernière de la branche 0.18, publiée le même jour que la 0.19.0.

Pour mettre à jour : télécharger la nouvelle archive, vérifier son champ `dist.integrity`, remplacer les fichiers (polices comprises), puis mettre à jour ce README.
