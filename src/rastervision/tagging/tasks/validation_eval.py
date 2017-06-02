from os.path import join, isfile
import json

from sklearn.metrics import fbeta_score
import numpy as np
import matplotlib as mpl
# For headless environments
mpl.use('Agg') # NOQA
import matplotlib.pyplot as plt

from rastervision.common.settings import VALIDATION
from rastervision.common.utils import plot_img_row, _makedirs

from rastervision.tagging.tasks.utils import compute_prediction


class Scores():
    """A set of scores for the performance of a model on a dataset."""
    def __init__(self, y_true, y_pred, all_tags):
        self.f2 = fbeta_score(y_true, y_pred, beta=2, average='samples')
        f2_subscores = fbeta_score(y_true, y_pred, beta=2, average=None)
        self.f2_subscores = dict(zip(all_tags, f2_subscores))

    def to_json(self):
        return json.dumps(self.__dict__, sort_keys=True, indent=4)

    def save(self, path):
        scores_json = self.to_json()
        with open(path, 'w') as scores_file:
            scores_file.write(scores_json)


def plot_prediction(generator, all_x, y_true, y_pred,
                    file_path):
    dataset = generator.dataset
    fig = plt.figure()

    nb_subplot_cols = 3 + len(generator.active_input_inds)
    grid_spec = mpl.gridspec.GridSpec(1, nb_subplot_cols)

    all_x = generator.calibrate_image(all_x)
    rgb_input_im = all_x[:, :, dataset.rgb_inds]
    imgs = [rgb_input_im]
    titles = ['RGB']

    ir_im = all_x[:, :, dataset.ir_ind]
    imgs.append(ir_im)
    titles.append('IR')

    ndvi_im = all_x[:, :, dataset.ndvi_ind]
    imgs.append(ndvi_im)
    titles.append('NDVI')

    plot_img_row(fig, grid_spec, 0, imgs, titles)

    add_pred_tags, remove_pred_tags = \
        generator.tag_store.get_tag_diff(y_true, y_pred)
    y_true_strs = sorted(generator.tag_store.binary_to_strs(y_true))

    y_true_strs = ', '.join(y_true_strs)
    add_pred_tags = ', '.join(add_pred_tags)
    remove_pred_tags = ', '.join(remove_pred_tags)
    tag_info = 'ground truth: {}\nfalse +: {}\nfalse -: {}'.format(
        y_true_strs, add_pred_tags, remove_pred_tags)
    fig.text(0.15, 0.35, tag_info, fontsize=5)

    plt.savefig(file_path, bbox_inches='tight', format='png', dpi=300)
    plt.close(fig)


def plot_predictions(run_path, model, options, generator):
    validation_plot_path = join(run_path, 'validation_plots')
    _makedirs(validation_plot_path)

    y_trues = []
    y_preds = []

    split_gen = generator.make_split_generator(
        VALIDATION, target_size=None,
        batch_size=options.batch_size, shuffle=False, augment=False,
        normalize=True, only_xy=False)

    for batch_ind, batch in enumerate(split_gen):
        y_probs = model.predict(batch.x)
        for sample_ind in range(batch.x.shape[0]):
            file_ind = batch.file_inds[sample_ind]
            all_x = np.squeeze(batch.all_x)

            y_pred = compute_prediction(
                y_probs[sample_ind, :], generator.dataset)
            y_true = generator.tag_store.get_tag_array([file_ind])[0, :]
            y_preds.append(np.expand_dims(y_pred, axis=0))
            y_trues.append(np.expand_dims(y_true, axis=0))

            is_mistake = not np.array_equal(y_true, y_pred)

            plot_path = join(
                validation_plot_path, '{}_debug.png'.format(file_ind))
            if is_mistake:
                plot_prediction(generator, all_x, y_true, y_pred, plot_path)

        if (options.nb_eval_samples is not None and
                batch_ind * options.batch_size >= options.nb_eval_samples):
            break

    y_trues = np.concatenate(y_trues, axis=0)
    y_preds = np.concatenate(y_preds, axis=0)
    return y_trues, y_preds


def validation_eval(run_path, model, options, generator):
    y_true, y_pred = plot_predictions(run_path, model, options, generator)

    scores = Scores(y_true, y_pred, generator.dataset.all_tags)
    scores_path = join(run_path, 'scores.json')
    scores.save(scores_path)
