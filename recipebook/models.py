import os
import re
import datetime
from unicodedata import normalize

import json
from werkzeug import generate_password_hash, check_password_hash
from bson import json_util
from mongoengine import (
        Document, EmbeddedDocument, Q,
        StringField, EmailField, IntField, FloatField,
        DateTimeField, ListField, EmbeddedDocumentField, ReferenceField)
import markdown2

from recipebook import config
from recipebook import photos


class User(Document):
    """Represents a user in the database"""

    username = StringField(primary_key=True)
    email = EmailField(required=True)
    real_name = StringField(default='')
    password = StringField(required=True)
    level = IntField(required=True, default=0)
    registration_date = DateTimeField()

    meta = {'collection': 'users'}

    #User levels
    (ADMIN, USER) = range(2)

    def set_password(self, password):
        self.password = unicode(generate_password_hash(password))

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def display_name(self):
        return self.real_name if self.real_name else self.username


def create_user(email, username, password, level=User.USER):
    user = User(email=email, username=username)
    if level in (User.USER, User.ADMIN):
        user.level = level
    else:
        raise ValueError("Invalid user level")
    user.set_password(password)
    return user


def get_user(login_name):
    """Get a user with either the username or email"""

    return User.objects(
        Q(username=login_name) |
        Q(email=login_name)).first()


class Ingredient(EmbeddedDocument):
    name = StringField(required=True)
    amount = FloatField()
    measure = StringField()

    @classmethod
    def from_json(cls, data):
        return cls(
                name=data['name'],
                amount=data['amount'],
                measure=data['measure'])


class IngredientGroup(EmbeddedDocument):
    title = StringField(default='')
    ingredients = ListField(EmbeddedDocumentField(Ingredient))

    @classmethod
    def from_json(cls, data):
        """Update data with dictionary from json data"""

        title = data['group']
        ingredients = [
                Ingredient.from_json(item) for item in data['ingredients']]
        return cls(title=title, ingredients=ingredients)


class Recipe(Document):
    """Represents a recipe document in the database"""

    title = StringField(required=True)
    title_slug = StringField(required=True, unique_with='user')
    description = StringField(default='')
    photo = StringField(default='')
    instructions = StringField()
    user = ReferenceField(User, dbref=True, required=True)
    tags = ListField(StringField())
    ungrouped_ingredients = ListField(EmbeddedDocumentField(Ingredient))
    ingredient_groups = ListField(EmbeddedDocumentField(IngredientGroup))
    date_added = DateTimeField()

    meta = {
            'collection': 'recipes',
            'indexes': [('user', 'title_slug')],
    }

    def load_json(self, json_data):
        """Update data from json string"""

        data = json.loads(json_data, object_hook=json_util.object_hook)
        for key in data:
            if key == 'title':
                self.title = data[key]
                self.title_slug = slugify(data[key])
            elif key == 'user':
                self.user = User.objects.get(username=data[key])
            elif key == 'ungrouped_ingredients':
                self.ungrouped_ingredients = []
                for item in data[key]:
                    ingredient = Ingredient.from_json(item)
                    self.ungrouped_ingredients.append(ingredient)
            elif key == 'ingredient_groups':
                self.ingredient_groups = []
                for group in data[key]:
                    ingredient_group = IngredientGroup.from_json(group)
                    self.ingredient_groups.append(ingredient_group)
            else:
                self.__setattr__(key, data[key])

    def html_instructions(self):
        return markdown2.markdown(self.instructions)

    def show_photo(self, width, height):
        return photos.url(self.photo, width, height)


def create_recipe(title, username, ingredients, description):
    """Create a new recipe

    ingredients is a dict with ingredient group names as keys
    and lists of ingredients for values
    """

    recipe = Recipe(title=title, description=description)
    recipe.user = User.objects.with_id(username)
    recipe.title_slug = slugify(title)
    ingredient_groups = [
            IngredientGroup(group=k, ingredients=v)
            for k, v in ingredients.items()]
    # Ungrouped ingredients are in a group with no name,
    # so remove them and put them in their own list
    ungrouped_ingredients = ingredient_groups['']
    del(ingredient_groups[''])
    recipe.ungrouped_ingredients = ungrouped_ingredients
    recipe.ingredient_groups = ingredient_groups
    recipe.date = datetime.datetime.utcnow()
    return recipe


_punct_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.]+')


def slugify(text, delim=u'-'):
    """Generates an ASCII-only slug."""

    result = []
    for word in _punct_re.split(unicode(text).lower()):
        word = normalize('NFKD', word).encode('ascii', 'ignore')
        if word:
            result.append(word)
    return unicode(delim.join(result))
