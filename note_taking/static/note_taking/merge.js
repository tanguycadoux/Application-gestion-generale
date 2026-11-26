// Fusion d'un enregistrement sur place (#472) : la note avait changé ailleurs depuis
// l'ouverture de l'éditeur (capture rapide, autre onglet), et la vue a réuni les deux
// textes. L'éditeur reçoit les lignes venues d'ailleurs, à changer dans le texte
// envoyé, et les applique comme une modification : le curseur, la sélection et ce qui
// a été tapé pendant l'enregistrement restent, ramenés sur le nouveau texte.
import { ChangeSet, StateEffect } from "@codemirror/state";
import { EditorView } from "@codemirror/view";

// Les lignes `from` à `to` (exclue, numérotées de 0) de `doc` remplacées par `lines`,
// en positions de CodeMirror.
export function lineChange(doc, { from, to, lines }) {
    const text = lines.join("\n");
    if (from === to) {
        // Ajout avant la ligne `from`, ou à la fin du texte.
        if (from < doc.lines) return { from: doc.line(from + 1).from, insert: `${text}\n` };
        return { from: doc.length, insert: `\n${text}` };
    }
    if (lines.length) {
        return { from: doc.line(from + 1).from, to: doc.line(to).to, insert: text };
    }
    // Lignes retirées, avec leur fin de ligne.
    if (to < doc.lines) return { from: doc.line(from + 1).from, to: doc.line(to + 1).from };
    if (from > 0) return { from: doc.line(from).to, to: doc.length };
    return { from: 0, to: doc.length };
}

// `note_form.js` signale l'envoi (`note:saving`), puis la fusion (`note:merge`, avec
// le texte envoyé et les lignes à changer) ; `detail.applied` dit qu'elle est faite.
export function followMerges(view, textarea) {
    let pending = null;
    view.dispatch({
        effects: StateEffect.appendConfig.of(
            EditorView.updateListener.of((update) => {
                if (pending && update.docChanged) {
                    pending.changes = pending.changes.compose(update.changes);
                }
            }),
        ),
    });
    textarea.addEventListener("note:saving", () => {
        const { doc } = view.state;
        pending = { doc, changes: ChangeSet.empty(doc.length) };
    });
    textarea.addEventListener("note:merge", (event) => {
        const { sent, edits } = event.detail;
        if (!pending || pending.doc.toString() !== sent) return;
        const { doc, changes } = pending;
        pending = null;
        const merge = ChangeSet.of(edits.map((edit) => lineChange(doc, edit)), doc.length);
        // Ramenées sur ce qui a été tapé depuis l'envoi.
        view.dispatch({ changes: merge.map(changes), userEvent: "input.merge" });
        event.detail.applied = true;
    });
}
