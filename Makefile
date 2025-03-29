dist: $(SOURCES)
	@python3 setup.py sdist bdist_wheel

pypi: dist
	@twine upload dist/* --repository gamest-retroarch-identifier-plugin

.PHONY: dist pypi
