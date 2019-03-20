import setuptools

setuptools.setup(
        name='repoman',
        version='0.2.0',
        author='Jarkko Oranen',
        author_email='oranenj@iki.fi',
        long_description='',
        long_description_content_type='text/markdown',
        packages=setuptools.find_packages(),
        classifiers=[
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: MIT License",
            "Operating System :: Linux",
            ],
        entry_points = {
            'console_scripts': ['repoman=repoman.repoman:main']
            }
        )
