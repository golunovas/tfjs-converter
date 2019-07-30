# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Interactive command line tool for tensorflow.js model conversion."""

from __future__ import print_function, unicode_literals

import os
import re
import json
import sys

from PyInquirer import prompt, style_from_dict, Token
from tensorflow.python.saved_model.loader_impl import parse_saved_model
from tensorflow.core.framework import types_pb2
from tensorflowjs.converters.converter import convert
# regex for recognizing valid url for TFHub module.
TFHUB_VALID_URL_REGEX = re.compile(
    # http:// or https://
    r'^(?:http)s?://', re.IGNORECASE)

# prompt style
prompt_style = style_from_dict({
    Token.Separator: '#6C6C6C',
    Token.QuestionMark: '#FF9D00 bold',
    # Token.Selected: '',  # default
    Token.Selected: '#5F819D',
    Token.Pointer: '#FF9D00 bold',
    Token.Instruction: '',  # default
    Token.Answer: '#5F819D bold',
    Token.Question: '',
})

KERAS_SAVED_MODEL = 'keras_saved_model'
KERAS_MODEL = 'keras'
TF_SAVED_MODEL = 'tf_saved_model'
TF_HUB = 'tf_hub'
TFJS_GRAPH_MODEL = 'tfjs_keras_model'
TFJS_LAYERS_MODEL = 'tfjs_layers_model'


def quantization_type(user_selection_quant):
  """Determine the quantization type based on user selection.
  Args:
    user_selection_quant: user selected quantization value.

  Returns:
    int: quantization parameter value for converter.
  """
  answer = None
  try:
    if '1/2' in user_selection_quant:
      answer = 2
    elif '1/4' in user_selection_quant:
      answer = 1
  except ValueError:
    answer = None
  return answer


def value_in_list(answers, key, values):
  """Determine user's answer for the key is in the value list.
  Args:
    answer: Dict of user's answers to the questions.
    key: question key.
    values: List of values to check from.
  """
  try:
    value = answers[key]
    return value in values
  except KeyError:
    return False


def get_tfjs_model_type(file):
  with open(file) as f:
    data = json.load(f)
    return data['format']


def detect_input_format(input_path):
  """Determine the input format from model's input path or file.
  Args:
    input_path: string of the input model path
  returns:
    string: detected input format
    string: normalized input path
  """
  input_path = input_path.lower()
  detected_input_format = None
  if re.match(TFHUB_VALID_URL_REGEX, input_path):
    detected_input_format = TF_HUB
  elif os.path.isdir(input_path):
    if any(fname.lower().endswith('.pb') for fname in os.listdir(input_path)):
      detected_input_format = TF_SAVED_MODEL
    else:
      for fname in os.listdir(input_path):
        fname = fname.lower()
        if fname.endswith('.json'):
          filename = os.path.join(input_path, fname)
          if get_tfjs_model_type(filename) == 'layers-model':
            input_path = os.path.join(input_path, fname)
            detected_input_format = TFJS_LAYERS_MODEL
            break
  elif os.path.isfile(input_path):
    if input_path.endswith('.hdf5'):
      detected_input_format = KERAS_MODEL
    elif input_path.endswith('.pb'):
      detected_input_format = TF_SAVED_MODEL
    elif (input_path.endswith('.json') and
          get_tfjs_model_type(input_path) == 'layers-model'):
      detected_input_format = TFJS_LAYERS_MODEL

  return detected_input_format, input_path


def input_path_message(answers):
  """Determine question for model's input path.
  Args:
    answer: Dict of user's answers to the questions
  """
  answer = answers['input_format']
  message = 'The original path seems to be wrong, '
  if answer == KERAS_MODEL:
    return message + 'what is the path of input HDF5 file?'
  elif answer == TF_HUB:
    return message + 'what is the TFHub module URL?'
  else:
    return message + 'what is the directory that contains the model?'


def validate_input_path(input_path, input_format):
  """validate the input path for given input format.
  Args:
    input_path: input path of the model.
    input_format: model format string.
  """
  path = os.path.expanduser(input_path)
  if not path:
    return 'Please enter a valid path'
  if input_format == TF_HUB:
    if re.match(TFHUB_VALID_URL_REGEX, path) is None:
      return """This is not an valid URL for TFHub module: %s,
        We expect a URL that starts with http(s)://""" % path
  elif not os.path.exists(path):
    return 'Nonexistent path for the model: %s' % path
  if input_format in [KERAS_SAVED_MODEL, TF_SAVED_MODEL]:
    is_dir = os.path.isdir(path)
    if not is_dir and not path.endswith('.pb'):
      return 'The path provided is not a directory or .pb file: %s' % path
    if is_dir and not any(f.endswith('.pb') for f in os.listdir(path)):
      return 'Did not find a .pb file inside the directory: %s' % path
  if input_format == TFJS_LAYERS_MODEL:
    is_dir = os.path.isdir(path)
    if not is_dir and not path.endswith('.json'):
      return 'The path provided is not a directory or .json file: %s' % path
    if is_dir and not any(f.endswith('.json') for f in os.listdir(path)):
      return 'Did not find a .pb file inside the directory: %s' % path
  if input_format == KERAS_MODEL:
    if not os.path.isfile(path):
      return 'The path provided is not a file: %s' % path
  return True


def expand_input_path(input_format, input_path):
  """expand the relative input path to absolute path, and add layers model file
  name to the end if input format is `tfjs_layers_model`.
  Args:
    output_path: input path of the model.
    input_format: model format string.
  Returns:
    string: return expanded input path.
  """
  input_path = os.path.expanduser(input_path)
  is_dir = os.path.isdir(input_path)
  if is_dir:
    for fname in os.listdir(input_path):
      if fname.endswith('.json'):
        filename = os.path.join(input_path, fname)
        return filename
  return input_path


def validate_output_path(output_path):
  """validate the input path for given input format.
  Args:
    output_path: input path of the model.
    input_format: model format string.
  Returns:
    bool: return true when the output directory does not exist.
  """
  output_path = os.path.expanduser(output_path)
  if not output_path:
    return 'Please provide a valid output path'
  if os.path.exists(output_path):
    return 'The output path already exists: %s' % output_path
  return True


def generate_arguments(params):
  """generate the tensorflowjs command string for the selected params.
  Args:
    params: user selected parameters for the conversion.
  Returns:
    list: the argument list for converter.
  """
  args = []
  not_param_list = ['input_path', 'output_path']
  no_false_param = ['split_weights_by_layer', 'skip_op_check']
  for key, value in sorted(params.items()):
    if key not in not_param_list and value is not None:
      if key in no_false_param:
        if value is True:
          args.append('--%s' % (key))
      else:
        args.append('--%s=%s' % (key, value))

  args.append(params['input_path'])
  args.append(params['output_path'])
  return args


def is_saved_model(input_format):
  """check if the input path contains saved model.
  Args:
    input_format: input model format.
  Returns:
    bool: whether this is for a saved model conversion.
  """
  return input_format == TF_SAVED_MODEL or \
      input_format == KERAS_SAVED_MODEL


def available_output_formats(answers):
  """generate the output formats for given input format.
  Args:
    ansowers: user selected parameter dict.
  """
  print(answers)
  input_format = answers['input_format']
  if input_format == KERAS_SAVED_MODEL:
    return [{
        'key': 'g',
        'name': 'Tensorflow.js Graph Model',
        'value': TFJS_GRAPH_MODEL,
    }, {
        'key': 'l',
        'name': 'TensoFlow.js Layers Model',
        'value': TFJS_LAYERS_MODEL,
    }]
  if input_format == TFJS_LAYERS_MODEL:
    return [{
        'key': 'k',
        'name': 'Keras Model (HDF5)',
        'value': KERAS_MODEL,
    }, {
        'key': 'l',
        'name': 'TensoFlow.js Layers Model',
        'value': TFJS_LAYERS_MODEL,
    }]
  return []


def available_tags(answers):
  """generate the available saved model tags from the proto file.
  Args:
    ansowers: user selected parameter dict.
  """
  print(answers)
  if is_saved_model(answers['input_format']):
    saved_model = parse_saved_model(answers['input_path'])
    tags = []
    for meta_graph in saved_model.meta_graphs:
      tags.append(",".join(meta_graph.meta_info_def.tags))
    return tags
  return []


def available_signature_names(answers):
  """generate the available saved model signatures from the proto file
    and selected tags.
  Args:
    ansowers: user selected parameter dict.
  """
  if is_saved_model(answers['input_format']):
    path = answers['input_path']
    tags = answers['saved_model_tags']
    saved_model = parse_saved_model(path)
    for meta_graph in saved_model.meta_graphs:
      if tags == ",".join(meta_graph.meta_info_def.tags):
        signatures = []
        for key in meta_graph.signature_def:
          input_nodes = meta_graph.signature_def[key].inputs
          output_nodes = meta_graph.signature_def[key].outputs
          signatures.append(
              {'value': key,
               'name': format_signature(key, input_nodes, output_nodes)})
        return signatures
  return []


def format_signature(name, input_nodes, output_nodes):
  string = "signature name: %s\n" % name
  string += "        inputs: \n%s" % format_nodes(input_nodes)
  string += "        outputs: \n%s" % format_nodes(output_nodes)
  return string


def format_nodes(nodes):
  string = ""
  for key in nodes:
    value = nodes[key]
    string += "              name: %s, " % value.name
    string += "dtype: %s, " % types_pb2.DataType.Name(value.dtype)
    if value.tensor_shape.unknown_rank:
      string += "shape: Unknown\n"
    else:
      string += "shape: %s\n" % [x.size for x in value.tensor_shape.dim]
  return string


def input_format_string(base, target_format, detected_format):
  if target_format == detected_format:
    return base + ' *'
  else:
    return base


def input_format_message(detected_input_format):
  message = 'What is your input model format? '
  if detected_input_format:
    message += '(auto-detected format is marked with *)'
  else:
    message += '(model format cannot be detected.) '
  return message


def input_formats(detected_format):
  formats = [{
      'key': 'k',
      'name': input_format_string('Keras (HDF5)', KERAS_MODEL,
                                  detected_format),
      'value': KERAS_MODEL
  }, {
      'key': 'e',
      'name': input_format_string('Tensorflow Keras Saved Model',
                                  KERAS_SAVED_MODEL,
                                  detected_format),
      'value': KERAS_SAVED_MODEL,
  }, {
      'key': 's',
      'name': input_format_string('Tensorflow Saved Model',
                                  TF_SAVED_MODEL,
                                  detected_format),
      'value': TF_SAVED_MODEL,
  }, {
      'key': 'h',
      'name': input_format_string('TFHub Module',
                                  TF_HUB,
                                  detected_format),
      'value': TF_HUB,
  }, {
      'key': 'l',
      'name': input_format_string('TensoFlow.js Layers Model',
                                  TFJS_LAYERS_MODEL,
                                  detected_format),
      'value': TFJS_LAYERS_MODEL,
  }]
  formats.sort(key=lambda x: x['value'] != detected_format)
  return formats


def main(dry_run):
  print('Weclome to TensorFlow.js converter.')
  input_path = [{
      'type': 'input',
      'name': 'input_path',
      'message': 'Please provide the path of model file or '
                 'the directory that contains model files. \n'
                 'If you are converting TFHub module please provide the URL.',
      'filter': os.path.expanduser,
      'validate':
          lambda path: 'Please enter a valid path' if not path else True
  }]

  input_params = prompt(input_path, style=prompt_style)
  detected_input_format, normalized_path = detect_input_format(
      input_params['input_path'])
  input_params['input_path'] = normalized_path

  formats = [
      {
          'type': 'list',
          'name': 'input_format',
          'message': input_format_message(detected_input_format),
          'choices': input_formats(detected_input_format)
      }, {
          'type': 'list',
          'name': 'output_format',
          'message': 'What is your output format?',
          'choices': available_output_formats,
          'when': lambda answers: value_in_list(answers, 'input_format',
                                                [KERAS_SAVED_MODEL,
                                                 TFJS_LAYERS_MODEL])
      }
  ]
  options = prompt(formats, input_params, style=prompt_style)
  message = input_path_message(options)

  questions = [
      {
          'type': 'input',
          'name': 'input_path',
          'message': message,
          'filter': lambda value: expand_input_path(
              value, options['input_format']),
          'validate': lambda value: validate_input_path(
              value, options['input_format']),
          'when': lambda answers: (not detect_input_format)
      },
      {
          'type': 'list',
          'name': 'saved_model_tags',
          'choices': available_tags,
          'message': 'What is tags for the saved model?',
          'when': lambda answers: is_saved_model(answers['input_format'])
      },
      {
          'type': 'list',
          'name': 'signature_name',
          'message': 'What is signature name of the model?',
          'choices': available_signature_names,
          'when': lambda answers: is_saved_model(answers['input_format'])
      },
      {
          'type': 'list',
          'name': 'quantization_bytes',
          'message': 'Do you want to compress the model? '
                     '(this will decrease the model precision.)',
          'choices': ['No compression, no accuracy loss.',
                      '2x compression, medium accuracy loss.',
                      '4x compression, highest accuracy loss.'],
          'filter': quantization_type
      },
      {
          'type': 'input',
          'name': 'weight_shard_size_byte',
          'message': 'Please enter shard size (in bytes) of the weight files?',
          'default': str(4 * 1024 * 1024),
          'when': lambda answers: value_in_list(answers, 'output_format',
                                                [TFJS_LAYERS_MODEL])
      },
      {
          'type': 'confirm',
          'name': 'split_weights_by_layer',
          'message': 'Do you want to split weights by layers?',
          'default': False,
          'when': lambda answers: value_in_list(answers, 'input_format',
                                                [TFJS_LAYERS_MODEL])
      },
      {
          'type': 'confirm',
          'name': 'skip_op_check',
          'message': 'Do you want to skip op validation? \n'
                     'This will allow conversion of unsupported ops, \n'
                     'you can implement them as custom ops in tfjs-converter.',
          'default': False,
          'when': lambda answers: value_in_list(answers, 'input_format',
                                                [TF_SAVED_MODEL, TF_HUB])
      },
      {
          'type': 'confirm',
          'name': 'strip_debug_ops',
          'message': 'Do you want to strip debug ops? \n'
                     'This will improve model execution performance.',
          'default': True,
          'when': lambda answers: value_in_list(answers, 'input_format',
                                                [TF_SAVED_MODEL, TF_HUB])
      },
      {
          'type': 'input',
          'name': 'output_path',
          'message': 'Which directory do you want to save '
                     'the converted model in?',
          'filter': os.path.expanduser,
          'validate': validate_output_path
      }
  ]
  params = prompt(questions, options, style=prompt_style)

  arguments = generate_arguments(params)
  if dry_run:
    print('converter command generated:')
    print('tensorflowjs_converter %s' % ' '.join(arguments))
  else:
    convert(arguments)
    print('file generated after conversion:')
    for entry in os.scandir(params['output_path']):
      print(entry.stat().st_size, entry.name)


if __name__ == '__main__':
  if len (sys.argv) > 2 or len(sys.argv) == 1 and not sys.argv[1] == 'dryrun':
    print("Usage: tensorflowjs_cli [--dryrun]")
    sys.exit (1)
  dry_run = sys.argv[1] == '--dryrun'
  main(dry_run)
